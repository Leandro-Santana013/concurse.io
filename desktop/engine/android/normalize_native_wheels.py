"""Adapt Android wheels to Chaquopy's loader and reject incompatible ELFs.

Flet's wheels ship dependencies under opt/lib or their package. Chaquopy's
dependency loader searches chaquopy/lib. Standard .so module names work with
both runtimes without depending on their different CPython ABI suffixes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
from pathlib import Path


def elf_info(data: bytes) -> dict:
    if data[:4] != b"\x7fELF" or data[4:6] != b"\x02\x01":
        raise ValueError("Expected a little-endian 64-bit ELF")
    machine = struct.unpack_from("<H", data, 18)[0]
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phcount = struct.unpack_from("<HH", data, 54)
    segments = [struct.unpack_from("<IIQQQQQQ", data, phoff + index * phsize) for index in range(phcount)]
    loads = [segment for segment in segments if segment[0] == 1]
    alignments = [segment[7] for segment in loads]
    if machine != 183 or not loads or any(value < 16384 for value in alignments):
        raise ValueError(f"Incompatible Android ELF: machine={machine}, PT_LOAD={alignments}")
    dynamic = next((segment for segment in segments if segment[0] == 2), None)
    soname = None
    needed = []
    if dynamic:
        tags = []
        for offset in range(dynamic[2], dynamic[2] + dynamic[5], 16):
            tag, value = struct.unpack_from("<qQ", data, offset)
            if tag == 0:
                break
            tags.append((tag, value))
        string_address = next((value for tag, value in tags if tag == 5), 0)
        string_offset = next((segment[2] + string_address - segment[3] for segment in loads
                              if segment[3] <= string_address < segment[3] + segment[5]), None)
        if string_offset is not None:
            def text_at(value):
                start = string_offset + value
                return data[start:data.index(b"\0", start)].decode("ascii")
            soname = next((text_at(value) for tag, value in tags if tag == 14), None)
            needed = [text_at(value) for tag, value in tags if tag == 1]
    return {"machine": machine, "load_alignments": alignments, "soname": soname, "needed": needed}


def normalize(root: Path) -> list[dict]:
    root = root.resolve(strict=True)
    report = []
    for variant_dir in [entry for entry in root.iterdir() if entry.is_dir()]:
        library_dir = variant_dir / "chaquopy" / "lib"
        for source in sorted(variant_dir.rglob("*")):
            if not source.is_file() or not re.search(r"\.so(?:\.\d+)*$", source.name):
                continue
            data = source.read_bytes()
            if data[:4] != b"\x7fELF":
                continue
            info = elf_info(data)
            target = source.with_name(re.sub(r"\.cpython-312[^.]*\.so$", ".so", source.name))
            if source.name.startswith("lib"):
                target = library_dir / (info["soname"] or source.name)
            if target != source:
                # All moves stay within this generated, verified task directory.
                if not target.resolve().is_relative_to(root):
                    raise ValueError("Native wheel target escaped the generated directory")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if target.read_bytes() != data:
                        raise ValueError(f"Conflicting shared library: {target.name}")
                    source.unlink()
                else:
                    shutil.move(str(source), str(target))
            report.append({"path": str(target.relative_to(root)).replace("\\", "/"),
                           "sha256": hashlib.sha256(data).hexdigest(), **info})
    (root / "native-wheel-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Validated and prepared {len(report)} ARM64 native libraries for 16 KB pages.", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    normalize(parser.parse_args().root)
