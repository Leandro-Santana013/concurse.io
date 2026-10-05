"""Audit all packaged ELFs, including Python's nested requirement archives."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
from posixpath import basename, dirname, join

from normalize_native_wheels import elf_info


def validate_dependency_locations(native: list[dict]) -> None:
    """SONAME-less wheels still need their libraries beside the extension.

    Chaquopy preloads named dependencies from chaquopy/lib. Android cannot
    reliably match a library loaded by absolute path to a DT_NEEDED name when
    that library has no SONAME, so its original $ORIGIN location must survive.
    Requirement archives share the same extraction directory on Android.
    """
    requirements = {
        item["path"].split("!/", 1)[1]: item
        for item in native
        if "requirements" in item["path"] and "!/" in item["path"]
    }
    shared = {
        basename(path): item for path, item in requirements.items()
        if path.startswith("chaquopy/lib/")
    }
    for name in shared:
        if ".cpython-" in name:
            raise ValueError(f"Python extension moved out of its package: {name}")
    for path, item in requirements.items():
        for needed in item["needed"]:
            dependency = shared.get(needed)
            if not dependency or dependency["soname"] == needed:
                continue
            sibling = join(dirname(path), needed)
            if sibling not in requirements:
                raise ValueError(
                    f"SONAME-less dependency {needed} missing beside {path}; "
                    "preserve the wheel's $ORIGIN library location"
                )


def audit(apk: Path, source_manifest: Path) -> dict:
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    allowed = {item["path"] for item in manifest["files"]}
    allowed |= {str(Path(item).with_suffix(".pyc")).replace("\\", "/") for item in allowed if item.endswith(".py")}
    native = []
    app_files = []
    assets = []

    def inspect(name: str, data: bytes):
        if data[:4] == b"\x7fELF":
            native.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), **elf_info(data)})

    with zipfile.ZipFile(apk) as package:
        for item in package.infolist():
            if item.is_dir():
                continue
            name = item.filename
            if Path(name).name == ".env" or name.endswith((".keystore", ".jks", ".pfx", ".p12", ".sqlite", ".db")):
                raise ValueError(f"Private data file packaged in APK: {name}")
            if name.startswith("lib/"):
                if not name.startswith("lib/arm64-v8a/"):
                    raise ValueError(f"Unexpected ABI in ARM64 release: {name}")
                inspect(name, package.read(item))
            elif name.startswith("assets/chaquopy/") and name.endswith(".imy"):
                assets.append(name)
                with zipfile.ZipFile(io.BytesIO(package.read(item))) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        if name == "assets/chaquopy/app.imy":
                            if member.filename not in allowed:
                                raise ValueError(f"Source outside engine allowlist: {member.filename}")
                            app_files.append(member.filename)
                        inspect(f"{name}!/{member.filename}", archive.read(member))
        required = ["mobile_engine", "fastapi_app", "routes/api_v1/exam_api", "services/pdf_pipeline/__init__"]
        for module in required:
            if not any(f"{module}.{suffix}" in app_files for suffix in ("py", "pyc")):
                raise ValueError(f"Missing engine module: {module}")
        if not any("requirements" in item for item in assets) or len(native) < 64:
            raise ValueError("Embedded Python native requirements are missing")
    validate_dependency_locations(native)
    return {"apk": str(apk.resolve()), "sha256": hashlib.file_digest(apk.open("rb"), "sha256").hexdigest(),
            "bytes": apk.stat().st_size, "source_count": len(app_files), "archives": assets, "native": native}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = audit(args.apk, args.manifest)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS: {len(report['native'])} ARM64 ELFs aligned to 16 KB; {report['source_count']} allowed engine files; {report['bytes']} bytes")
