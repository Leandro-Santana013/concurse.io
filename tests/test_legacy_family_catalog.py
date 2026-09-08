import json
from pathlib import Path
import re

from services.pdf_pipeline.legacy.family_catalog import (
    build_legacy_family_catalog,
    normalize_family_alias,
)


def test_export_matches_current_parser_inventory():
    path = Path(__file__).resolve().parents[1] / "data/legacy_family_catalog.json"
    assert json.loads(path.read_text(encoding="utf-8")) == build_legacy_family_catalog()


def test_catalog_patterns_are_usable_and_do_not_claim_pdf_validation():
    catalog = build_legacy_family_catalog()
    for family in catalog["families"]:
        header = re.compile(family["patterns"]["header"])
        options = re.compile(family["patterns"]["options"])
        assert header.search("1. Enunciado da questão")
        sample = "(C) Certo" if family["legacy_family"] == "TRUE_FALSE_ITEM" else "(A) Alternativa"
        assert options.search(sample)
        assert family["validation_status"] == "pending_pdf_validation"
        assert family["validated_reference_exam_ids"] == []


def test_aliases_and_legacy_rule_associations():
    assert normalize_family_alias(" Fundação Getúlio Vargas ") == "FUNDACAOGETULIOVARGAS"
    assert normalize_family_alias("Avança-SP") == normalize_family_alias("AVANCA SP")
    catalog = build_legacy_family_catalog()
    rules = {rule["rule_id"]: rule for rule in catalog["legacy_rules"]}
    assert rules["ibam"]["candidate_family_ids"] == ["legacy-municipal-prefixed"]
    assert rules["dataprev"]["candidate_family_ids"] == ["legacy-true-false-item"]
    assert rules["fgv"]["candidate_family_ids"] == ["legacy-standard-academic"]
    families = {family["family_id"]: family for family in catalog["families"]}
    assert families["legacy-universal"]["is_fallback"]
    assert families["legacy-universal"]["aliases"] == []
