"""Registry for legacy parser adapters and their known rule families."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from .adapter import (
    BancaLegacyParserAdapter,
    HybridLegacyParserAdapter,
    LegacyParserAdapter,
    LegacyParserContext,
    LegacyRule,
)


LEGACY_RULES: tuple[LegacyRule, ...] = (
    LegacyRule(
        name="dataprev",
        signals=("DATAPREV", "QUADRIX"),
        source_modules=(
            "services.pdf_pipeline.hybrid_extractor",
            "services.pdf_pipeline.formatters.banca_clusterizer",
        ),
        notes="Dataprev/Quadrix rules remain in the hybrid parser and banca family patterns.",
    ),
    LegacyRule(
        name="ibam",
        signals=("IBAM", "INSTITUTO BRASILEIRO DE ADMINISTRACAO MUNICIPAL"),
        source_modules=(
            "services.pdf_pipeline.hybrid_extractor",
            "services.pdf_pipeline.formatters.banca_clusterizer",
            "services.gabarito.gabarito_service",
        ),
        notes="IBAM layout and answer-key table rules remain distributed across existing modules.",
    ),
    LegacyRule(
        name="idcap",
        signals=("IDCAP", "IDECAP"),
        source_modules=(
            "services.pdf_pipeline.hybrid_extractor",
            "services.pdf_pipeline.formatters.banca_clusterizer",
            "services.pdf_pipeline.media.diagram_cropper",
        ),
        notes="IDCAP-specific behavior is preserved as legacy fallback and regression input.",
    ),
    LegacyRule(
        name="cebraspe",
        signals=("CEBRASPE", "CESPE"),
        source_modules=(
            "services.pdf_pipeline.hybrid_extractor",
            "services.pdf_pipeline.formatters.banca_clusterizer",
        ),
        notes="Certo/Errado behavior is still provided by the hybrid parser.",
    ),
    LegacyRule(
        name="fgv",
        signals=("FGV", "FUNDACAO GETULIO VARGAS"),
        source_modules=("services.pdf_pipeline.hybrid_extractor",),
        notes="FGV numeric header handling remains in the legacy parser.",
    ),
    LegacyRule(
        name="fcc",
        signals=("FCC", "FUNDACAO CARLOS CHAGAS"),
        source_modules=("services.pdf_pipeline.hybrid_extractor",),
        notes="FCC is represented for registry and regression coverage.",
    ),
    LegacyRule(
        name="vunesp",
        signals=("VUNESP",),
        source_modules=("services.pdf_pipeline.hybrid_extractor",),
        notes="Vunesp is represented for registry and regression coverage.",
    ),
    LegacyRule(
        name="aocp",
        signals=("AOCP", "INSTITUTO AOCP"),
        source_modules=("services.pdf_pipeline.hybrid_extractor",),
        notes="AOCP is represented for registry and regression coverage.",
    ),
    LegacyRule(
        name="consulplan",
        signals=("CONSULPLAN",),
        source_modules=("services.pdf_pipeline.hybrid_extractor",),
        notes="Consulplan is represented for registry and regression coverage.",
    ),
    LegacyRule(
        name="fundatec",
        signals=("FUNDATEC",),
        source_modules=("services.pdf_pipeline.hybrid_extractor",),
        notes="Fundatec is represented for registry and regression coverage.",
    ),
)


class LegacyParserRegistry:
    """Resolve a named or best-supported legacy adapter."""

    def __init__(self, adapters: Optional[Iterable[LegacyParserAdapter]] = None) -> None:
        self._adapters: Dict[str, LegacyParserAdapter] = {}
        for adapter in adapters or ():
            self.register(adapter)

    @staticmethod
    def _key(name: str) -> str:
        return str(name).strip().lower()

    def register(self, adapter: LegacyParserAdapter) -> None:
        self._adapters[self._key(adapter.name)] = adapter

    def get(self, name: str) -> LegacyParserAdapter:
        return self._adapters[self._key(name)]

    def names(self) -> tuple[str, ...]:
        return tuple(self._adapters.keys())

    def resolve(self, context: Optional[LegacyParserContext] = None) -> LegacyParserAdapter:
        resolved_context = context or LegacyParserContext()
        return max(
            self._adapters.values(),
            key=lambda adapter: adapter.supports(resolved_context),
        )


def build_default_legacy_registry() -> LegacyParserRegistry:
    """Build the Phase 1 inventory while keeping one implementation seam."""

    delegate = HybridLegacyParserAdapter()
    registry = LegacyParserRegistry([delegate])
    for rule in LEGACY_RULES:
        registry.register(BancaLegacyParserAdapter(rule, delegate))
    return registry
