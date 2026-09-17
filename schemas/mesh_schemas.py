from typing import List

from pydantic import BaseModel, Field, field_validator

from services.p2p.content_store import normalize_asset_id


class MeshAnnounceRequest(BaseModel):
    node_id: str = Field(min_length=8, max_length=128)
    endpoint: str = Field(min_length=8, max_length=500)
    asset_ids: List[str] = Field(default_factory=list, max_length=10000)
    lease_seconds: int = Field(default=120, ge=30, le=3600)

    @field_validator("asset_ids")
    @classmethod
    def validate_asset_ids(cls, values: List[str]) -> List[str]:
        normalized = []
        seen = set()
        for value in values:
            asset_id = normalize_asset_id(value)
            if asset_id is None:
                raise ValueError("asset_ids contém um identificador inválido")
            if asset_id in seen:
                continue
            seen.add(asset_id)
            normalized.append(asset_id)
        return normalized


class MeshPeerSchema(BaseModel):
    node_id: str
    endpoint: str
    asset_count: int = 0
    last_seen: str


class MeshProvidersSchema(BaseModel):
    asset_id: str
    providers: List[MeshPeerSchema] = Field(default_factory=list)
