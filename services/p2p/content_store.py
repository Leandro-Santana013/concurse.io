"""Armazenamento local endereçado pelo conteúdo para a malha de provas."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from services.exam_assets import asset_id_from_bytes


ASSET_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def normalize_asset_id(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if ASSET_ID_PATTERN.fullmatch(normalized) else None


class ContentAddressedStore:
    """Guarda blobs por digest, com gravação atômica e verificação integral."""

    def __init__(self, root: str | Path | None = None):
        configured = root or os.environ.get("MESH_CONTENT_DIR")
        if configured:
            self.root = Path(configured).expanduser().resolve()
        else:
            self.root = (Path(__file__).resolve().parents[2] / "mesh_data" / "content").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, asset_id: str) -> Path:
        normalized = normalize_asset_id(asset_id)
        if normalized is None:
            raise ValueError("asset_id inválido")
        return self.root / normalized.removeprefix("sha256:")

    def has(self, asset_id: str) -> bool:
        try:
            return self.path_for(asset_id).is_file()
        except ValueError:
            return False

    def put_bytes(self, asset_id: str, data: bytes) -> Path:
        expected = normalize_asset_id(asset_id)
        if expected is None or asset_id_from_bytes(data) != expected:
            raise ValueError("O conteúdo não corresponde ao asset_id informado")
        target = self.path_for(expected)
        if target.is_file():
            return target
        self._atomic_write(target, data)
        return target

    def put_file(self, asset_id: str, source: str | Path) -> Path:
        expected = normalize_asset_id(asset_id)
        if expected is None:
            raise ValueError("asset_id inválido")
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        digest = hashlib.sha256()
        with source_path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if f"sha256:{digest.hexdigest()}" != expected:
            raise ValueError("O arquivo não corresponde ao asset_id informado")

        target = self.path_for(expected)
        if target.is_file():
            return target
        with source_path.open("rb") as source_stream:
            self._atomic_write_stream(target, source_stream)
        return target

    def read_bytes(self, asset_id: str) -> bytes:
        path = self.path_for(asset_id)
        data = path.read_bytes()
        if asset_id_from_bytes(data) != normalize_asset_id(asset_id):
            raise IOError("Blob corrompido no armazenamento da malha")
        return data

    def _atomic_write(self, target: Path, data: bytes) -> None:
        from io import BytesIO

        self._atomic_write_stream(target, BytesIO(data))

    def _atomic_write_stream(self, target: Path, source_stream) -> None:
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.root,
                prefix=f".{target.name}.",
                suffix=".part",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                while chunk := source_stream.read(1024 * 1024):
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    pass
