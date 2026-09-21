"""Análise de distribuição de categorias nas provas IBAM disponíveis.

As provas de Santos (2016 e 2020) possuem faixas oficiais de disciplinas,
mas os blocos de Conhecimentos Específicos misturam subáreas. O índice usa
essas faixas como controle de integridade e aplica, dentro delas, uma
classificação temática revisada questão a questão. Assim, Administração,
Arquivologia, Redação Oficial e Informática permanecem visíveis como
categorias próprias, sem perder o grupo amplo da prova.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


UNCATEGORIZED = "Não classificada"


def _round_one(value: float) -> float:
    """Arredonda percentuais no padrão convencional, incluindo 0,05 para cima."""

    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class CategoryRule:
    start: int
    end: int
    label: str
    group: str


@dataclass(frozen=True)
class IbamExamProfile:
    key: str
    year: int
    display_title: str
    title_markers: Tuple[str, ...]
    rules: Tuple[CategoryRule, ...]
    granular_rules: Tuple[CategoryRule, ...] = ()


LANGUAGE_GROUP = "Língua Portuguesa"
MATH_GROUP = "Matemática e Raciocínio Lógico"
GENERAL_GROUP = "Conhecimentos Gerais / Atualidades"
SPECIFIC_GROUP = "Conhecimentos Específicos"


IBAM_EXAM_PROFILES: Tuple[IbamExamProfile, ...] = (
    IbamExamProfile(
        key="santos-2020-oficial-administracao",
        year=2020,
        display_title="IBAM · 2020 · Prefeitura de Santos — Oficial de Administração",
        title_markers=("SANTOS", "OFICIAL DE ADMINISTRA"),
        rules=(
            CategoryRule(1, 10, LANGUAGE_GROUP, LANGUAGE_GROUP),
            CategoryRule(11, 15, "Matemática", MATH_GROUP),
            CategoryRule(16, 18, GENERAL_GROUP, GENERAL_GROUP),
            CategoryRule(19, 40, SPECIFIC_GROUP, SPECIFIC_GROUP),
        ),
        granular_rules=(
            CategoryRule(1, 10, LANGUAGE_GROUP, LANGUAGE_GROUP),
            CategoryRule(11, 15, MATH_GROUP, MATH_GROUP),
            CategoryRule(16, 18, GENERAL_GROUP, GENERAL_GROUP),
            CategoryRule(19, 32, "Informática", SPECIFIC_GROUP),
            CategoryRule(33, 35, "Administração", SPECIFIC_GROUP),
            CategoryRule(36, 38, "Redação Oficial", SPECIFIC_GROUP),
            CategoryRule(39, 39, "Administração", SPECIFIC_GROUP),
            CategoryRule(40, 40, "Arquivologia", SPECIFIC_GROUP),
        ),
    ),
    IbamExamProfile(
        key="santos-2016-oficial-administracao",
        year=2016,
        display_title="IBAM · 2016 · Prefeitura de Santos — Oficial de Administração",
        title_markers=("SANTOS", "OFICIAL DE ADMINISTRA"),
        rules=(
            CategoryRule(1, 10, LANGUAGE_GROUP, LANGUAGE_GROUP),
            CategoryRule(11, 15, "Raciocínio Lógico e Matemática", MATH_GROUP),
            CategoryRule(16, 24, "Conhecimentos Gerais e Atualidades", GENERAL_GROUP),
            CategoryRule(
                25,
                35,
                "Conhecimentos Específicos — Administração Pública, Arquivologia e Redação Oficial",
                SPECIFIC_GROUP,
            ),
            CategoryRule(36, 50, "Conhecimentos Específicos — Informática", SPECIFIC_GROUP),
        ),
        granular_rules=(
            CategoryRule(1, 10, LANGUAGE_GROUP, LANGUAGE_GROUP),
            CategoryRule(11, 15, MATH_GROUP, MATH_GROUP),
            CategoryRule(16, 24, GENERAL_GROUP, GENERAL_GROUP),
            CategoryRule(25, 25, "História local / Patrimônio de Santos", GENERAL_GROUP),
            CategoryRule(26, 29, "Administração", SPECIFIC_GROUP),
            CategoryRule(30, 32, "Arquivologia", SPECIFIC_GROUP),
            CategoryRule(33, 35, "Redação Oficial", SPECIFIC_GROUP),
            CategoryRule(36, 50, "Informática", SPECIFIC_GROUP),
        ),
    ),
)


def _normalized_text(value: Any) -> str:
    """Normaliza acentos, caixa e artefatos de OCR para comparações internas."""

    raw = str(value or "").replace("�", "")
    without_accents = unicodedata.normalize("NFKD", raw)
    without_accents = "".join(char for char in without_accents if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip().upper()


def _exam_identity(exam: Any) -> str:
    return " ".join(
        part
        for part in (
            getattr(exam, "title", ""),
            getattr(exam, "source_url", ""),
            getattr(exam, "gabarito_url", ""),
        )
        if part
    )


def _profile_matches(exam: Any, profile: IbamExamProfile) -> bool:
    identity = _normalized_text(_exam_identity(exam))
    return str(profile.year) in identity and all(marker in identity for marker in profile.title_markers)


def is_ibam_exam(exam: Any) -> bool:
    """Retorna se o registro é um perfil conhecido ou tem marcador IBAM explícito."""

    if any(_profile_matches(exam, profile) for profile in IBAM_EXAM_PROFILES):
        return True
    return "IBAM" in _normalized_text(_exam_identity(exam))


def _profile_for_exam(exam: Any) -> Optional[IbamExamProfile]:
    for profile in IBAM_EXAM_PROFILES:
        if _profile_matches(exam, profile):
            return profile
    return None


def _question_position(question: Any, fallback_position: int) -> int:
    raw_number = str(getattr(question, "numero_questao", "") or "").strip()
    match = re.match(r"^(\d+)", raw_number)
    if match:
        number = int(match.group(1))
        if number > 0:
            return number

    question_index = getattr(question, "question_index", None)
    if isinstance(question_index, int) and question_index >= 0:
        return question_index + 1
    return fallback_position


def _question_sort_key(question_with_position: Tuple[int, Any]) -> Tuple[int, int]:
    position, question = question_with_position
    question_id = getattr(question, "id", 0) or 0
    return position, int(question_id)


def _canonical_label(raw_subject: Any) -> Tuple[str, str]:
    raw = str(raw_subject or "").strip()
    normalized = _normalized_text(raw)
    if not raw or normalized in {"GERAL", "NAO CLASSIFICADA"}:
        return UNCATEGORIZED, UNCATEGORIZED

    if "PORTUGUES" in normalized or "GRAMATICA" in normalized or "INTERPRETACAO" in normalized:
        return LANGUAGE_GROUP, LANGUAGE_GROUP
    if "MATEM" in normalized or "RACIOC" in normalized:
        return raw, MATH_GROUP
    if "ATUAL" in normalized or "CONHECIMENTOS GERAIS" in normalized or "REGIONAL" in normalized:
        return raw, GENERAL_GROUP
    if any(term in normalized for term in ("INFORMAT", "ADMINISTR", "ARQUIVO", "REDACAO OFICIAL")):
        return raw, SPECIFIC_GROUP
    return raw, raw


def _category_for_question(
    profile: Optional[IbamExamProfile],
    question: Any,
    position: int,
) -> Tuple[str, str]:
    if profile is not None:
        for rule in (*profile.granular_rules, *profile.rules):
            if rule.start <= position <= rule.end:
                return rule.label, rule.group
    return _canonical_label(getattr(question, "subject", ""))


def _compress_positions(positions: Iterable[int]) -> str:
    values = sorted(set(int(value) for value in positions))
    if not values:
        return "—"

    ranges: List[str] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(str(start) if start == previous else f"{start}–{previous}")
        start = previous = value
    ranges.append(str(start) if start == previous else f"{start}–{previous}")
    return ", ".join(ranges)


def _ordered_questions(questions: Sequence[Any]) -> List[Tuple[int, Any]]:
    positioned = [
        (_question_position(question, index), question)
        for index, question in enumerate(questions, start=1)
    ]
    return sorted(positioned, key=_question_sort_key)


def _exam_result(exam: Any, questions: Sequence[Any]) -> Dict[str, Any]:
    profile = _profile_for_exam(exam)
    ordered_questions = _ordered_questions(questions)
    total_questions = len(ordered_questions)
    buckets: Dict[str, Dict[str, Any]] = {}

    for position, question in ordered_questions:
        label, group = _category_for_question(profile, question, position)
        # ``label`` é a categoria temática exibida. ``group`` permanece como
        # camada ampla para medir cobertura e preservar a faixa oficial.
        bucket_key = label
        bucket = buckets.setdefault(
            bucket_key,
            {"name": bucket_key, "category_group": group, "count": 0, "question_numbers": []},
        )
        bucket["count"] += 1
        bucket["question_numbers"].append(position)

    categories = []
    for bucket in buckets.values():
        count = int(bucket["count"])
        categories.append(
            {
                "name": bucket["name"],
                "category_group": bucket["category_group"],
                "question_count": count,
                "percentage": _round_one((count / total_questions * 100) if total_questions else 0.0),
                "question_range": _compress_positions(bucket["question_numbers"]),
            }
        )

    categories.sort(key=lambda item: (-item["question_count"], item["name"].casefold()))
    for rank, category in enumerate(categories, start=1):
        category["rank"] = rank

    classified_questions = sum(
        category["question_count"] for category in categories if category["category_group"] != UNCATEGORIZED
    )
    top_category = categories[0] if categories else None
    display_title = profile.display_title if profile else str(getattr(exam, "title", "Prova IBAM"))

    return {
        "exam_id": int(getattr(exam, "id", 0)),
        "title": display_title,
        "source_title": str(getattr(exam, "title", "") or display_title),
        "year": profile.year if profile else None,
        "question_count": total_questions,
        "classified_question_count": classified_questions,
        "unclassified_question_count": total_questions - classified_questions,
        "coverage_percentage": _round_one((classified_questions / total_questions * 100) if total_questions else 0.0),
        "top_category": top_category,
        "categories": categories,
    }


def analyze_ibam_exams(
    exams: Sequence[Any],
    questions_by_exam: Mapping[int, Sequence[Any]],
) -> Dict[str, Any]:
    """Monta o índice de peso das categorias, ordenado do maior para o menor."""

    ibam_exams = [exam for exam in exams if is_ibam_exam(exam)]
    exam_results = [
        _exam_result(exam, questions_by_exam.get(int(getattr(exam, "id", 0)), ()))
        for exam in ibam_exams
    ]
    exam_results.sort(key=lambda item: (-(item["question_count"] or 0), item["title"].casefold()))

    total_questions = sum(item["question_count"] for item in exam_results)
    classified_questions = sum(item["classified_question_count"] for item in exam_results)
    category_names = sorted(
        {
            category["name"]
            for exam in exam_results
            for category in exam["categories"]
            if category["category_group"] != UNCATEGORIZED
        },
        key=str.casefold,
    )

    category_averages = []
    for category_name in category_names:
        exam_weights = []
        total_category_questions = 0
        for exam in exam_results:
            category_count = sum(
                category["question_count"]
                for category in exam["categories"]
                if category["name"] == category_name
            )
            total_category_questions += category_count
            question_count = exam["question_count"]
            exam_weights.append(
                {
                    "exam_id": exam["exam_id"],
                    "question_count": category_count,
                    "percentage": _round_one((category_count / question_count * 100) if question_count else 0.0),
                }
            )

        average_question_count = (
            sum(item["question_count"] for item in exam_weights) / len(exam_weights)
            if exam_weights
            else 0.0
        )
        average_weight = (
            sum(item["percentage"] for item in exam_weights) / len(exam_weights)
            if exam_weights
            else 0.0
        )
        category_averages.append(
            {
                "name": category_name,
                "exam_count": len(exam_weights),
                "average_question_count": _round_one(average_question_count),
                "average_weight_percentage": _round_one(average_weight),
                "question_count": total_category_questions,
                "aggregate_percentage": _round_one((total_category_questions / total_questions * 100) if total_questions else 0.0),
                "exam_weights": exam_weights,
            }
        )

    category_averages.sort(
        key=lambda item: (-item["average_weight_percentage"], item["name"].casefold())
    )
    for rank, category in enumerate(category_averages, start=1):
        category["rank"] = rank

    dominant_category = category_averages[0] if category_averages else None
    return {
        "available": bool(exam_results),
        "exam_count": len(exam_results),
        "question_count": total_questions,
        "classified_question_count": classified_questions,
        "unclassified_question_count": total_questions - classified_questions,
        "coverage_percentage": _round_one((classified_questions / total_questions * 100) if total_questions else 0.0),
        "dominant_category": dominant_category,
        "category_averages": category_averages,
        "exams": exam_results,
        "methodology": {
            "category_source": "Faixas oficiais das provas IBAM de Santos (2016 e 2020), com classificação temática revisada dentro dos blocos específicos; a questão 25/2016 foi mantida como História local / Patrimônio de Santos por causa do enunciado. O campo subject é usado como fallback em outras provas IBAM.",
            "average_definition": "Média aritmética do percentual de cada categoria em cada prova; categoria ausente vale 0%.",
            "ranking_definition": "Cada prova e cada índice são ordenados pelo maior número de questões.",
        },
    }


__all__ = [
    "IBAM_EXAM_PROFILES",
    "analyze_ibam_exams",
    "is_ibam_exam",
]
