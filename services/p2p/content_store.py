"""Armazenamento local endereçado pelo conteúdo para a malha de provas."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable, Mapping

from services.exam_assets import asset_id_from_bytes


ASSET_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
DEFAULT_CHUNK_SIZE = 1024 * 1024
MIN_CHUNK_SIZE = 256 * 1024
MAX_CHUNK_SIZE = 8 * 1024 * 1024
MANIFEST_VERSION = 1


def normalize_asset_id(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if ASSET_ID_PATTERN.fullmatch(normalized) else None


def configured_chunk_size(value: object | None = None) -> int:
    """Retorna o tamanho de bloco usado pela malha, com limites seguros.

    O valor pode ser configurado por ``MESH_CHUNK_SIZE``. Limitar o tamanho
    evita tanto milhares de requisições em celulares quanto respostas grandes
    demais para um nó com pouca memória.
    """

    raw = value if value is not None else os.environ.get("MESH_CHUNK_SIZE")
    try:
        parsed = int(raw) if raw not in (None, "") else DEFAULT_CHUNK_SIZE
    except (TypeError, ValueError):
        parsed = DEFAULT_CHUNK_SIZE
    return max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, parsed))


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

    def manifest_path_for(self, asset_id: str) -> Path:
        normalized = normalize_asset_id(asset_id)
        if normalized is None:
            raise ValueError("asset_id inválido")
        return self.root / f"{normalized.removeprefix('sha256:')}.manifest.json"

    def has(self, asset_id: str) -> bool:
        try:
            return self.path_for(asset_id).is_file()
        except ValueError:
            return False

    def has_verified(self, asset_id: str) -> bool:
        """Confirma que o arquivo local ainda corresponde ao digest anunciado."""

        try:
            normalized = normalize_asset_id(asset_id)
            if not normalized:
                return False
            # Depois do primeiro manifesto, tamanho + mtime tornam a checagem
            # de cache O(1); se o arquivo mudou, manifest_for refaz o hash
            # completo e recusa o conteúdo corrompido.
            self.manifest_for(normalized)
            return True
        except (OSError, ValueError):
            return False

    def put_bytes(self, asset_id: str, data: bytes) -> Path:
        expected = normalize_asset_id(asset_id)
        if expected is None or asset_id_from_bytes(data) != expected:
            raise ValueError("O conteúdo não corresponde ao asset_id informado")
        target = self.path_for(expected)
        if target.is_file() and self._file_matches(target, expected):
            return target
        self._atomic_write(target, data)
        self._remove_manifest(target)
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
        if target.is_file() and self._file_matches(target, expected):
            return target
        with source_path.open("rb") as source_stream:
            self._atomic_write_stream(target, source_stream)
        self._remove_manifest(target)
        return target

    def read_bytes(self, asset_id: str) -> bytes:
        path = self.path_for(asset_id)
        data = path.read_bytes()
        if asset_id_from_bytes(data) != normalize_asset_id(asset_id):
            raise IOError("Blob corrompido no armazenamento da malha")
        return data

    def manifest_for(self, asset_id: str, *, chunk_size: int | None = None) -> dict:
        """Gera ou lê o manifesto content-addressed de um blob completo."""

        normalized = normalize_asset_id(asset_id)
        if normalized is None:
            raise ValueError("asset_id inválido")
        path = self.path_for(normalized)
        if not path.is_file():
            raise FileNotFoundError(path)
        configured = configured_chunk_size(chunk_size)
        manifest_path = self.manifest_path_for(normalized)
        try:
            cached = json.loads(manifest_path.read_text(encoding="utf-8"))
            if self._valid_manifest(cached, normalized, configured, path):
                return cached
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

        manifest = self._build_manifest(normalized, path, configured)
        self._atomic_write_json(manifest_path, manifest)
        return manifest

    def read_chunk(
        self,
        asset_id: str,
        chunk_index: int,
        *,
        chunk_size: int | None = None,
        manifest: Mapping | None = None,
    ) -> tuple[bytes, dict]:
        """Lê um bloco e valida seu hash antes de entregá-lo ao peer."""

        try:
            index = int(chunk_index)
        except (TypeError, ValueError):
            raise ValueError("chunk_index inválido")
        selected_manifest = dict(manifest or self.manifest_for(asset_id, chunk_size=chunk_size))
        chunks = selected_manifest.get("chunks")
        if not isinstance(chunks, list) or index < 0 or index >= len(chunks):
            raise IndexError("chunk_index fora do manifesto")
        descriptor = chunks[index]
        if not isinstance(descriptor, Mapping):
            raise ValueError("manifesto de blocos inválido")
        try:
            offset = int(descriptor["offset"])
            size = int(descriptor["size"])
            expected_hash = str(descriptor["sha256"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("descritor de bloco inválido")
        if offset < 0 or size < 0:
            raise ValueError("descritor de bloco inválido")
        path = self.path_for(asset_id)
        with path.open("rb") as stream:
            stream.seek(offset)
            data = stream.read(size)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_hash or len(data) != size:
            raise IOError("Bloco corrompido no armazenamento da malha")
        return data, dict(descriptor)

    def put_chunks(
        self,
        asset_id: str,
        chunks: Iterable[bytes],
        *,
        manifest: Mapping,
    ) -> Path:
        """Monta blocos verificados em um arquivo usando uma troca atômica."""

        normalized = normalize_asset_id(asset_id)
        if normalized is None or str(manifest.get("asset_id")) != normalized:
            raise ValueError("manifesto não corresponde ao asset_id")
        descriptors = manifest.get("chunks")
        if not isinstance(descriptors, list):
            raise ValueError("manifesto de blocos inválido")

        target = self.path_for(normalized)
        temporary_path: str | None = None
        digest = hashlib.sha256()
        total = 0
        received_count = 0
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.root,
                prefix=f".{target.name}.",
                suffix=".part",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                for index, data in enumerate(chunks):
                    if index >= len(descriptors):
                        raise ValueError("quantidade de blocos excede o manifesto")
                    descriptor = descriptors[index]
                    if not isinstance(descriptor, Mapping):
                        raise ValueError("descritor de bloco inválido")
                    if int(descriptor.get("index", index)) != index:
                        raise ValueError(f"índice do bloco {index} não corresponde ao manifesto")
                    expected_size = int(descriptor["size"])
                    expected_hash = str(descriptor["sha256"])
                    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_hash:
                        raise ValueError(f"bloco {index} não corresponde ao manifesto")
                    temporary.write(data)
                    digest.update(data)
                    total += len(data)
                    received_count += 1
                if received_count != len(descriptors):
                    raise ValueError("quantidade de blocos incompleta")
                if total != int(manifest.get("size", -1)):
                    raise ValueError("tamanho final não corresponde ao manifesto")
                if f"sha256:{digest.hexdigest()}" != normalized:
                    raise ValueError("hash final não corresponde ao asset_id")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
            self._remove_manifest(target)
            return target
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _file_matches(path: Path, expected: str) -> bool:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        except OSError:
            return False
        return f"sha256:{digest.hexdigest()}" == expected

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

    @staticmethod
    def _valid_manifest(
        manifest: object,
        asset_id: str,
        chunk_size: int,
        path: Path,
    ) -> bool:
        if not isinstance(manifest, dict):
            return False
        try:
            if (
                int(manifest.get("version")) != MANIFEST_VERSION
                or str(manifest.get("asset_id")) != asset_id
                or int(manifest.get("chunk_size")) != chunk_size
                or int(manifest.get("size")) != path.stat().st_size
                or int(manifest.get("mtime_ns")) != int(path.stat().st_mtime_ns)
            ):
                return False
            chunks = manifest.get("chunks")
            return isinstance(chunks, list) and int(manifest.get("chunk_count")) == len(chunks)
        except (OSError, TypeError, ValueError):
            return False

    @staticmethod
    def _build_manifest(asset_id: str, path: Path, chunk_size: int) -> dict:
        total_size = path.stat().st_size
        chunks: list[dict] = []
        full_digest = hashlib.sha256()
        offset = 0
        with path.open("rb") as stream:
            while True:
                data = stream.read(chunk_size)
                if not data:
                    break
                chunk_digest = hashlib.sha256(data).hexdigest()
                chunks.append({
                    "index": len(chunks),
                    "offset": offset,
                    "size": len(data),
                    "sha256": chunk_digest,
                })
                full_digest.update(data)
                offset += len(data)
        if total_size == 0:
            chunks.append({
                "index": 0,
                "offset": 0,
                "size": 0,
                "sha256": hashlib.sha256(b"").hexdigest(),
            })
        if f"sha256:{full_digest.hexdigest()}" != asset_id:
            if total_size == 0 and asset_id == f"sha256:{hashlib.sha256(b'').hexdigest()}":
                pass
            else:
                raise IOError("Blob corrompido no armazenamento da malha")
        return {
            "version": MANIFEST_VERSION,
            "asset_id": asset_id,
            "size": total_size,
            "mtime_ns": int(path.stat().st_mtime_ns),
            "chunk_size": chunk_size,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }

    @staticmethod
    def _atomic_write_json(target: Path, payload: Mapping) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".part",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                temporary.write(encoded)
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

    @staticmethod
    def _remove_manifest(target: Path) -> None:
        try:
            target.with_name(f"{target.name}.manifest.json").unlink(missing_ok=True)
        except OSError:
            pass
