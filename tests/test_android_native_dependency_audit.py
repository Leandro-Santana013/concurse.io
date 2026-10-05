"""Catch APKs which contain every ELF but cannot load their PDF extensions."""
from pathlib import Path
import sys
import struct

import pytest


ENGINE = Path(__file__).resolve().parents[1] / "desktop" / "engine" / "android"
sys.path.insert(0, str(ENGINE))
from audit_apk import validate_dependency_locations
from normalize_native_wheels import normalize


def library(path, needed=(), soname=None):
    return {"path": f"assets/chaquopy/requirements-common.imy!/{path}",
            "needed": list(needed), "soname": soname}


def test_pdf_dependency_moved_out_of_origin_is_rejected():
    native = [library("pymupdf/_extra.so", ["libmupdfcpp.so"]),
              library("chaquopy/lib/libmupdfcpp.so")]
    with pytest.raises(ValueError, match="libmupdfcpp.so missing beside pymupdf/_extra.so"):
        validate_dependency_locations(native)


def test_pdf_origin_copy_and_named_preloaded_dependencies_are_accepted():
    native = [library("pymupdf/_extra.so", ["libmupdfcpp.so", "libmupdf.so"]),
              library("chaquopy/lib/libmupdfcpp.so", ["libmupdf.so"]),
              library("pymupdf/libmupdfcpp.so", ["libmupdf.so"]),
              library("chaquopy/lib/libmupdf.so", soname="libmupdf.so")]
    validate_dependency_locations(native)


def test_normalizing_wheels_preserves_origin_dependencies_and_lib_python_module(tmp_path):
    # Minimal ARM64 ELF metadata: one aligned load segment, no SONAME.
    # This test checks installation layout; device instrumentation loads the
    # real native wheel binaries and exercises PDF/OCR execution.
    data = bytearray(512)
    data[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", data, 18, 183)
    struct.pack_into("<Q", data, 32, 64)
    struct.pack_into("<HH", data, 54, 56, 1)
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, 512, 512, 16384)
    common = tmp_path / "common"
    for relative in ("pymupdf/libmupdfcpp.so", "shapely/lib.cpython-312-aarch64-linux-android.so"):
        target = common / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    normalize(tmp_path)
    normalize(tmp_path)  # Gradle can rerun the adapter on an existing output.
    assert (common / "pymupdf/libmupdfcpp.so").read_bytes() == data
    assert (common / "chaquopy/lib/libmupdfcpp.so").read_bytes() == data
    assert (common / "shapely/lib.so").read_bytes() == data
    assert not (common / "chaquopy/lib/lib.so").exists()
    assert not (common / "chaquopy/lib/lib.cpython-312-aarch64-linux-android.so").exists()
