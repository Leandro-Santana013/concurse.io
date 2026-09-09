"""Candidate detection and feature engineering for the physical document model."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import statistics
import unicodedata
from typing import Any, Mapping, Optional

from ..layout.models import ElementLayout, LayoutAnalysis
from ..model import BBox, DocumentModel, PhysicalElement
from .config import CandidateDetectorConfig
from .features import FeatureSchemaV1, FeatureVector
from .legacy import LegacyEvidenceProvider
from .models import Candidate, CandidateDetection


_QUESTION_TOKEN_RE = re.compile(r"\b(?:QUESTAO|ITEM|Q)\b", re.IGNORECASE)
_EXPLICIT_HEADER_RE = re.compile(
    r"^\s*(?:QUESTAO|ITEM|Q)\s*\.?\s*0*(\d{1,3})\s*(?:[\.\-:;\)\u2013\u2014])?\s*(.*)$",
    re.IGNORECASE,
)
_NUMERIC_HEADER_RE = re.compile(
    r"^\s*\(?\s*0*(\d{1,3})\s*(?P<punct>[\.\-:;\)\u2013\u2014])?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_OPTION_LABEL_RE = re.compile(
    r"^\s*(?:"
    r"(?P<label>[A-Ea-e])\s*(?:\(\s*\)|[\.\-:;\)])"
    r"|\(\s*(?P<paren>[A-Ea-e])\s*\)"
    r"|\[\s*(?P<bracket>[A-Ea-e])\s*\]"
    r"|(?P<checkbox>[\u2610\u2611\u25a1\u25a2\u25a3\u25cb\u25cf])"
    r"|(?P<empty_checkbox>\[\s*[xX ]\s*\]|\(\s*[xX ]\s*\))"
    r"|(?P<bullet>[\u2022\u00b7\u25e6\u25cf\u25cb\u25aa\u25ab\-])"
    r")\s*"
)
_CONTEXT_MARKER_RE = re.compile(
    r"\b(?:TEXTO|INSTRUCAO|LEIA|CONSIDERE|COM BASE|PARA RESPONDER|QUESTOES?)\b",
    re.IGNORECASE,
)


@dataclass
class _TextLine:
    id: str
    page_index: int
    text: str
    bbox: BBox
    source_element_ids: list[str]
    order_index: int
    column_id: Optional[int]
    font_size: Optional[float]
    bold: bool
    italic: bool
    style_cluster_id: Optional[int]


@dataclass(frozen=True)
class _HeaderInfo:
    line: _TextLine
    number: int
    explicit: bool
    regex_kind: str
    regex_score: float
    is_integer: bool
    has_question_token: bool


class CandidateDetector:
    """Deep interface for turning physical/layout evidence into hypotheses.

    Interface:
        ``detect(document_model, layout_analysis) -> CandidateDetection``

    The detector emits alternatives and evidence; it does not produce the
    final question AST or mutate the legacy question dictionary contract.
    """

    def __init__(
        self,
        config: Optional[CandidateDetectorConfig] = None,
        *,
        legacy_evidence_provider: Optional[LegacyEvidenceProvider] = None,
    ) -> None:
        self.config = config or CandidateDetectorConfig()
        self._legacy_provider = legacy_evidence_provider

    def detect(
        self,
        document: DocumentModel,
        layout_analysis: Optional[LayoutAnalysis] = None,
        *,
        legacy_metadata: Optional[Mapping[str, Any]] = None,
    ) -> CandidateDetection:
        if layout_analysis is None:
            from ..layout.analyzer import LayoutAnalyzer

            layout_analysis = LayoutAnalyzer().analyze(document)

        provider = self._legacy_provider or LegacyEvidenceProvider(
            document,
            metadata=legacy_metadata,
        )
        index = _LayoutIndex(document, layout_analysis)
        lines = _build_text_lines(document, index)
        headers = [item for line in lines if (item := _parse_header(line, self.config))]
        header_infos = [item for item in headers if isinstance(item, _HeaderInfo)]
        header_line_ids = {item.line.id for item in header_infos}

        option_groups = self._detect_option_groups(
            document,
            lines,
            header_line_ids,
            index,
            provider,
        )
        question_headers = self._build_question_headers(
            header_infos,
            lines,
            option_groups,
            index,
            provider,
        )
        subjects = self._detect_subjects(lines, header_line_ids, provider)
        contexts = self._detect_contexts(
            lines,
            question_headers,
            header_line_ids,
            provider,
        )

        warnings: list[str] = []
        if not question_headers:
            warnings.append("no_question_header_candidates")
        if any(candidate.score < self.config.min_question_header_score for candidate in question_headers):
            warnings.append("low_confidence_question_header_candidates")
        return CandidateDetection(
            question_headers=question_headers,
            option_groups=option_groups,
            subjects=subjects,
            contexts=contexts,
            warnings=warnings,
        )

    def _build_question_headers(
        self,
        infos: list[_HeaderInfo],
        lines: list[_TextLine],
        option_groups: list[Candidate],
        index: "_LayoutIndex",
        provider: LegacyEvidenceProvider,
    ) -> list[Candidate]:
        if not infos:
            return []
        ordered_infos = sorted(infos, key=lambda item: (item.line.order_index, item.line.id))
        median_font = _median(
            [
                float(line.font_size)
                for line in lines
                if line.font_size is not None and not index.is_noise(line)
            ]
        ) or 1.0
        result: list[Candidate] = []
        for position, info in enumerate(ordered_infos):
            line = info.line
            previous = ordered_infos[position - 1] if position else None
            following = ordered_infos[position + 1] if position + 1 < len(ordered_infos) else None
            prev_delta = info.number - previous.number if previous else 0
            next_delta = following.number - info.number if following else 0
            sequential = _sequential_score(prev_delta, next_delta)
            option_below = _option_below_score(info, option_groups, following)
            body_below = _body_below_score(info, lines, following, option_groups, index)
            same_alignment = _alignment_score(info, ordered_infos, index)
            same_style = _style_score(info, ordered_infos, index)
            gap_before, gap_after = _line_gaps(info, lines, index)
            vertical_structure = min(
                1.0,
                0.55 * float(body_below > 0.0)
                + 0.35 * float(option_below > 0.0)
                + 0.10 * min(1.0, gap_after / 0.04),
            )
            legacy = provider.header_evidence(line.text)
            legacy_score = min(
                1.0,
                max(
                    float(legacy.get("legacy_bank_header_match", 0.0)),
                    float(legacy.get("legacy_bank_rule_count", 0.0)),
                ),
            )
            text = line.text
            alphanumeric = [char for char in text if char.isalnum()]
            uppercase_ratio = sum(char.isupper() for char in alphanumeric) / max(len(alphanumeric), 1)
            digit_ratio = sum(char.isdigit() for char in text) / max(len(text), 1)
            layout = index.layout_by_id.get(line.source_element_ids[0])
            column = layout.column_id if layout else -1
            header_style_similarity = min(
                1.0,
                0.55 * float(line.bold)
                + 0.35 * float((line.font_size or 0.0) >= median_font * 1.08)
                + 0.10 * same_style,
            )
            question_x_similarity = same_alignment
            features = FeatureVector(
                schema_version=self.config.feature_schema_version,
                values={
                    "content.is_integer": float(info.is_integer),
                    "content.integer_value_norm": min(
                        1.0,
                        info.number / max(self.config.max_question_number, 1),
                    ),
                    "content.has_question_token": float(info.has_question_token),
                    "content.regex_score": info.regex_score,
                    "content.text_length": float(len(text)),
                    "content.uppercase_ratio": uppercase_ratio,
                    "content.digit_ratio": digit_ratio,
                    "geometry.x0": float(line.bbox.nx0),
                    "geometry.y0": float(line.bbox.ny0),
                    "geometry.width": float(line.bbox.width / max(index.page_width(line.page_index), 1e-9)),
                    "geometry.height": float(line.bbox.height / max(index.page_height(line.page_index), 1e-9)),
                    "geometry.column": float(column if column is not None else -1),
                    "style.font_size_body_ratio": float((line.font_size or 0.0) / max(median_font, 1e-9)),
                    "style.bold": float(line.bold),
                    "style.italic": float(line.italic),
                    "style.cluster_frequency": index.style_frequency(line.style_cluster_id),
                    "sequence.prev_numeric_delta": float(prev_delta),
                    "sequence.next_numeric_delta": float(next_delta),
                    "sequence.reading_distance": float(
                        line.order_index - previous.line.order_index if previous else 0
                    ),
                    "context.gap_before": float(gap_before),
                    "context.gap_after": float(gap_after),
                    "context.option_group_below": float(option_below),
                    "context.body_below": float(body_below),
                    "context.header_footer_penalty": float(index.noise_penalty(line)),
                    "profile.header_style_similarity": header_style_similarity,
                    "profile.question_x_similarity": question_x_similarity,
                    "legacy.bank_rule_score": legacy_score,
                },
            )
            evidence = {
                "numeric": float(info.is_integer or info.number > 0),
                "sequential": sequential,
                "same_alignment": same_alignment,
                "same_style_cluster": same_style,
                "options_below": option_below,
                "regex": info.regex_score,
                "vertical_structure": vertical_structure,
                "legacy_bank_header_match": legacy.get("legacy_bank_header_match", 0.0),
                "legacy_bank_rule_score": legacy_score,
                "header_footer_penalty": index.noise_penalty(line),
            }
            weights = self.config.weights
            score_breakdown = {
                "numeric": weights.numeric * evidence["numeric"],
                "sequential": weights.sequential * sequential,
                "same_alignment": weights.same_alignment * same_alignment,
                "same_style_cluster": weights.same_style_cluster * same_style,
                "options_below": weights.options_below * option_below,
                "regex": weights.regex * info.regex_score,
                "vertical_structure": weights.vertical_structure * vertical_structure,
                "legacy_bonus": min(weights.legacy_bonus, weights.legacy_bonus * legacy_score),
            }
            if index.noise_penalty(line):
                score_breakdown["header_footer_penalty"] = -0.15 * index.noise_penalty(line)
            score = min(1.0, sum(score_breakdown.values()))
            accepted = (
                score >= self.config.min_question_header_score
                or (info.explicit and score >= self.config.explicit_question_min_score)
            )
            if not accepted:
                continue
            candidate = Candidate(
                id=f"question-header:{line.id}",
                type="QUESTION_HEADER",
                score=round(score, 8),
                evidence={key: float(value) for key, value in evidence.items()},
                metadata={
                    "question_number": info.number,
                    "line_text": line.text,
                    "reading_index": line.order_index,
                    "explicit_question_token": info.explicit,
                    "regex_kind": info.regex_kind,
                    "accepted": True,
                    "legacy_evidence_provider": "hybrid_extractor_rules",
                    "feature_schema_version": FeatureSchemaV1.version,
                },
                source_element_ids=list(line.source_element_ids),
                features=features,
                page_index=line.page_index,
                bbox=line.bbox,
                score_breakdown=score_breakdown,
            )
            result.append(candidate)
        return result

    def _detect_option_groups(
        self,
        document: DocumentModel,
        lines: list[_TextLine],
        header_line_ids: set[str],
        index: "_LayoutIndex",
        provider: LegacyEvidenceProvider,
    ) -> list[Candidate]:
        groups: list[list[_TextLine]] = []
        ordered = sorted(lines, key=lambda item: (item.order_index, item.id))
        index_by_line = {line.id: position for position, line in enumerate(ordered)}
        consumed: set[str] = set()
        for position, line in enumerate(ordered):
            if line.id in header_line_ids or line.id in consumed:
                continue
            marker = _option_marker(line.text)
            if marker is None:
                continue
            group = [line]
            consumed.add(line.id)
            previous = line
            for following in ordered[position + 1 :]:
                if following.id in header_line_ids:
                    break
                following_marker = _option_marker(following.text)
                if following_marker is None:
                    continue
                if not _same_option_column(previous, following, index):
                    break
                if _normalized_gap(previous, following, index) > self.config.max_option_gap_norm:
                    break
                group.append(following)
                consumed.add(following.id)
                previous = following
                if len(group) >= self.config.max_option_group_size:
                    break
            if len(group) >= self.config.min_option_group_size:
                groups.append(group)

        # A repeated, aligned run without labels is still a possible option
        # group. This is deliberately conservative: four or five lines only.
        by_column: dict[tuple[int, Optional[int]], list[_TextLine]] = {}
        for line in ordered:
            if line.id in header_line_ids or line.id in consumed:
                continue
            by_column.setdefault((line.page_index, index.column(line)), []).append(line)
        for column_lines in by_column.values():
            for start in range(0, max(0, len(column_lines) - self.config.min_unlabelled_option_group_size + 1)):
                group = column_lines[start : start + self.config.max_option_group_size]
                if len(group) < self.config.min_unlabelled_option_group_size:
                    continue
                if not _repeated_option_geometry(group, index):
                    continue
                if any(line.id in consumed for line in group):
                    continue
                groups.append(group)
                consumed.update(line.id for line in group)
                break

        candidates: list[Candidate] = []
        for group in groups:
            candidate = self._option_candidate(group, lines, index, provider)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _option_candidate(
        self,
        group: list[_TextLine],
        lines: list[_TextLine],
        index: "_LayoutIndex",
        provider: LegacyEvidenceProvider,
    ) -> Optional[Candidate]:
        group = sorted(group, key=lambda item: (item.order_index, item.id))
        labels: list[str] = []
        marker_types: list[str] = []
        for line in group:
            label, marker_type = _option_marker(line.text) or (None, "")
            if label:
                labels.append(label)
            if marker_type:
                marker_types.append(marker_type)
        alignment = 1.0 - min(1.0, _spread([line.bbox.nx0 for line in group]) / 0.05)
        gaps = [
            _normalized_gap(first, second, index)
            for first, second in zip(group[:-1], group[1:])
        ]
        spacing = 1.0 - min(1.0, _spread(gaps) / 0.03) if gaps else 0.5
        style = _group_style_similarity(group)
        preceding_header = _nearest_preceding_header(group[0], lines, index)
        below_statement = (
            1.0
            if preceding_header is not None
            and _same_option_column(preceding_header, group[0], index)
            and _normalized_gap(preceding_header, group[0], index) <= 0.45
            else 0.25
        )
        style_ids = [line.style_cluster_id for line in group if line.style_cluster_id is not None]
        visual_cluster = min(1.0, len(set(style_ids)) / max(len(group), 1)) if style_ids else style
        joined = "\n".join(line.text for line in group)
        legacy = provider.option_evidence(joined)
        label_evidence = min(1.0, len(labels) / max(4.0, float(len(group))))
        if not labels and len(group) >= self.config.min_unlabelled_option_group_size:
            label_evidence = 0.45
        score_breakdown = {
            "label_evidence": 0.30 * label_evidence,
            "repeated_alignment": 0.20 * alignment,
            "spacing_recurrence": 0.15 * spacing,
            "same_style": 0.15 * style,
            "below_statement": 0.10 * below_statement,
            "visual_cluster": 0.05 * visual_cluster,
            "legacy_option_pattern": 0.05 * legacy.get("legacy_option_pattern", 0.0),
        }
        score = min(1.0, sum(score_breakdown.values()))
        if score < 0.25:
            return None
        bbox = _union_bbox([line.bbox for line in group])
        return Candidate(
            id=f"option-group:p{group[0].page_index}:{group[0].id}",
            type="OPTION_GROUP",
            score=round(score, 8),
            evidence={
                "label_evidence": label_evidence,
                "repeated_alignment": alignment,
                "spacing_recurrence": spacing,
                "same_style": style,
                "below_statement": below_statement,
                "visual_cluster": visual_cluster,
                "legacy_option_pattern": legacy.get("legacy_option_pattern", 0.0),
            },
            metadata={
                "labels": labels,
                "marker_types": marker_types,
                "count": len(group),
                "line_ids": [line.id for line in group],
                "reading_index": group[0].order_index,
                "preceding_header_line_id": preceding_header.id if preceding_header else None,
                "legacy_evidence_provider": "extract_options_from_chunk",
            },
            source_element_ids=[
                element_id
                for line in group
                for element_id in line.source_element_ids
            ],
            page_index=group[0].page_index,
            bbox=bbox,
            score_breakdown=score_breakdown,
        )

    def _detect_subjects(
        self,
        lines: list[_TextLine],
        header_line_ids: set[str],
        provider: LegacyEvidenceProvider,
    ) -> list[Candidate]:
        result: list[Candidate] = []
        for line in lines:
            if line.id in header_line_ids or not line.text.strip():
                continue
            if len(line.text.strip()) > self.config.max_subject_line_chars:
                continue
            evidence = provider.subject_evidence(line.text)
            if not evidence.get("legacy_subject_pattern") and not evidence.get("legacy_subject_classifier"):
                continue
            try:
                from ...fallbacks.subject_classifier import format_subject_title

                subject = format_subject_title(line.text)
            except Exception:
                subject = line.text.strip()
            score = min(
                1.0,
                0.75 * evidence.get("legacy_subject_pattern", 0.0)
                + 0.25 * evidence.get("legacy_subject_classifier", 0.0),
            )
            result.append(
                Candidate(
                    id=f"subject:{line.id}",
                    type="SUBJECT",
                    score=round(score, 8),
                    evidence=evidence,
                    metadata={
                        "subject": subject,
                        "line_text": line.text,
                        "reading_index": line.order_index,
                        "legacy_evidence_provider": "SUBJECT_REGEX+classifier",
                    },
                    source_element_ids=list(line.source_element_ids),
                    page_index=line.page_index,
                    bbox=line.bbox,
                    score_breakdown={
                        "legacy_subject_pattern": 0.75 * evidence.get("legacy_subject_pattern", 0.0),
                        "legacy_subject_classifier": 0.25 * evidence.get("legacy_subject_classifier", 0.0),
                    },
                )
            )
        return result

    def _detect_contexts(
        self,
        lines: list[_TextLine],
        question_headers: list[Candidate],
        header_line_ids: set[str],
        provider: LegacyEvidenceProvider,
    ) -> list[Candidate]:
        ordered = sorted(lines, key=lambda item: (item.order_index, item.id))
        line_by_id = {line.id: line for line in ordered}
        header_by_line_id = {
            line_id: candidate
            for candidate in question_headers
            for line_id in [
                _line_id_for_source(candidate.source_element_ids, ordered)
            ]
            if line_id is not None
        }
        result: list[Candidate] = []
        for position, line in enumerate(ordered):
            if line.id in header_line_ids:
                continue
            if not _CONTEXT_MARKER_RE.search(_normalize(line.text)):
                continue
            numbers = _context_question_numbers(line.text)
            end_position = len(ordered)
            for following_position, following in enumerate(
                ordered[position + 1 :],
                start=position + 1,
            ):
                if following.id in header_line_ids:
                    end_position = following_position
                    break
            body_lines = [
                item
                for item in ordered[position:end_position]
                if item.order_index >= line.order_index
            ][: self.config.max_context_source_elements]
            body_text = "\n".join(item.text for item in body_lines).strip()
            if len(body_text) < self.config.context_min_body_chars and not numbers:
                continue
            if not numbers:
                following_headers = [
                    candidate
                    for candidate in question_headers
                    if int(candidate.metadata.get("reading_index", -1)) > line.order_index
                ][:3]
                numbers = [
                    int(candidate.metadata["question_number"])
                    for candidate in following_headers
                    if candidate.metadata.get("question_number") is not None
                ]
            evidence = provider.context_evidence(line.text)
            evidence["body_length"] = min(1.0, len(body_text) / 500.0)
            score = min(
                1.0,
                0.45 * evidence.get("legacy_context_pattern", 0.0)
                + 0.30 * evidence.get("legacy_context_question_range", 0.0)
                + 0.25 * evidence["body_length"],
            )
            source_ids = [element_id for item in body_lines for element_id in item.source_element_ids]
            result.append(
                Candidate(
                    id=f"context:{line.id}",
                    type="CONTEXT_BLOCK",
                    score=round(score, 8),
                    evidence=evidence,
                    metadata={
                        "question_numbers": numbers,
                        "line_text": line.text,
                        "reading_index": line.order_index,
                        "text": body_text,
                        "legacy_evidence_provider": "layout.extract_context_blocks_rules",
                    },
                    source_element_ids=source_ids,
                    page_index=line.page_index,
                    bbox=_union_bbox([item.bbox for item in body_lines]),
                    score_breakdown={
                        "legacy_context_pattern": 0.45 * evidence.get("legacy_context_pattern", 0.0),
                        "legacy_context_question_range": 0.30 * evidence.get("legacy_context_question_range", 0.0),
                        "body_length": 0.25 * evidence["body_length"],
                    },
                )
            )
        return result


class _LayoutIndex:
    def __init__(self, document: DocumentModel, analysis: LayoutAnalysis) -> None:
        self.document = document
        self.analysis_pages = list(analysis.pages)
        self.layout_by_id: dict[str, ElementLayout] = {
            item.element_id: item
            for page in analysis.pages
            for item in page.elements
        }
        self.roles = analysis.zones.element_roles
        self._style_frequencies: dict[Optional[int], float] = {}
        for page in analysis.pages:
            for item in page.elements:
                if item.style_cluster_id is not None:
                    self._style_frequencies[item.style_cluster_id] = (
                        self._style_frequencies.get(item.style_cluster_id, 0.0) + 1.0
                    )
        total = max(sum(self._style_frequencies.values()), 1.0)
        self._style_frequencies = {
            key: value / total for key, value in self._style_frequencies.items()
        }

    def column(self, line: _TextLine) -> Optional[int]:
        values = {
            self.layout_by_id[element_id].column_id
            for element_id in line.source_element_ids
            if element_id in self.layout_by_id
            and self.layout_by_id[element_id].column_id is not None
        }
        return next(iter(values)) if len(values) == 1 else None

    def page_width(self, page_index: int) -> float:
        return float(self.document.pages[page_index].width)

    def page_height(self, page_index: int) -> float:
        return float(self.document.pages[page_index].height)

    def is_noise(self, line: _TextLine) -> bool:
        return any(
            role in {"HEADER_NOISE", "FOOTER_NOISE"}
            for element_id in line.source_element_ids
            for role in self.roles.get(element_id, [])
        )

    def noise_penalty(self, line: _TextLine) -> float:
        return 1.0 if self.is_noise(line) else 0.0

    def style_frequency(self, style_cluster_id: Optional[int]) -> float:
        return float(self._style_frequencies.get(style_cluster_id, 0.0))


def _build_text_lines(document: DocumentModel, index: _LayoutIndex) -> list[_TextLine]:
    order_map: dict[str, int] = {}
    cursor = 0
    for page in sorted(document.pages, key=lambda item: item.page_index):
        layout = next(
            (item for item in getattr(index, "analysis_pages", []) if item.page_index == page.page_index),
            None,
        )
        if layout is not None:
            for element_id in layout.reading_order.sequence:
                order_map[element_id] = cursor
                cursor += 1
    text_elements = [
        element
        for page in document.pages
        for element in page.elements
        if element.kind == "text" and str(element.text or "").strip()
    ]
    for element in sorted(text_elements, key=lambda item: (item.page_index, item.bbox.ny0, item.bbox.nx0, item.id)):
        if element.id not in order_map:
            order_map[element.id] = cursor
            cursor += 1
    groups: dict[tuple[Any, ...], list[PhysicalElement]] = {}
    for element in text_elements:
        metadata = element.metadata or {}
        layout = index.layout_by_id.get(element.id)
        column = layout.column_id if layout else None
        if metadata.get("block_index") is not None and metadata.get("line_index") is not None:
            key = (element.page_index, "native", metadata.get("block_index"), metadata.get("line_index"))
        else:
            key = (
                element.page_index,
                "geometry",
                column,
                round(float(element.bbox.ny0) / 0.006),
            )
        groups.setdefault(key, []).append(element)
    lines: list[_TextLine] = []
    for group in groups.values():
        group.sort(key=lambda item: (float(item.bbox.nx0), order_map.get(item.id, 0), item.id))
        first = group[0]
        bbox = _union_bbox([item.bbox for item in group])
        style_cluster_ids = {
            index.layout_by_id[item.id].style_cluster_id
            for item in group
            if item.id in index.layout_by_id and index.layout_by_id[item.id].style_cluster_id is not None
        }
        lines.append(
            _TextLine(
                id=f"line:p{first.page_index}:{first.id}",
                page_index=first.page_index,
                text=" ".join(str(item.text or "").strip() for item in group).strip(),
                bbox=bbox,
                source_element_ids=[item.id for item in group],
                order_index=min(order_map.get(item.id, 0) for item in group),
                column_id=column,
                font_size=_median([float(item.font_size) for item in group if item.font_size is not None]),
                bold=any(item.bold for item in group),
                italic=any(item.italic for item in group),
                style_cluster_id=next(iter(style_cluster_ids)) if len(style_cluster_ids) == 1 else None,
            )
        )
    return sorted(lines, key=lambda item: (item.order_index, item.id))


def _parse_header(line: _TextLine, config: CandidateDetectorConfig) -> Optional[_HeaderInfo]:
    normalized = _normalize(line.text)
    explicit_match = _EXPLICIT_HEADER_RE.match(normalized)
    if explicit_match:
        number = int(explicit_match.group(1))
        if 1 <= number <= config.max_question_number:
            return _HeaderInfo(
                line=line,
                number=number,
                explicit=True,
                regex_kind="explicit_question_token",
                regex_score=1.0,
                is_integer=not bool(explicit_match.group(2).strip()),
                has_question_token=True,
            )
        return None
    numeric_match = _NUMERIC_HEADER_RE.match(normalized)
    if not numeric_match:
        return None
    number = int(numeric_match.group(1))
    if not 1 <= number <= config.max_question_number:
        return None
    punctuation = numeric_match.group("punct") or ""
    rest = (numeric_match.group("rest") or "").strip()
    if not punctuation and rest:
        return None
    if rest and not punctuation:
        return None
    if rest and not re.match(r"^[A-ZÀ-Ü\"'“‘(\[]", rest):
        return None
    return _HeaderInfo(
        line=line,
        number=number,
        explicit=False,
        regex_kind="numeric_punctuation" if punctuation else "standalone_integer",
        regex_score=0.86 if punctuation else 0.72,
        is_integer=not bool(rest),
        has_question_token=bool(_QUESTION_TOKEN_RE.search(normalized)),
    )


def _option_marker(text: str) -> Optional[tuple[Optional[str], str]]:
    match = _OPTION_LABEL_RE.match(str(text or ""))
    if not match:
        return None
    label = match.group("label") or match.group("paren") or match.group("bracket")
    marker_type = "label" if label else (
        "checkbox" if match.group("checkbox") or match.group("empty_checkbox") else "bullet"
    )
    return (label.upper() if label else None, marker_type)


def _option_below_score(
    info: _HeaderInfo,
    option_groups: list[Candidate],
    following: Optional[_HeaderInfo],
) -> float:
    values: list[float] = []
    for group in option_groups:
        if group.page_index is None or group.bbox is None:
            continue
        if group.page_index < info.line.page_index:
            continue
        if following and group.page_index == following.line.page_index and group.bbox.ny0 >= following.line.bbox.ny0:
            continue
        if group.page_index == info.line.page_index and group.bbox.ny0 <= info.line.bbox.ny1:
            continue
        distance = (
            group.bbox.ny0 - info.line.bbox.ny1
            if group.page_index == info.line.page_index
            else 0.12
        )
        if distance <= 0.42:
            values.append(max(0.0, 1.0 - distance / 0.42) * group.score)
    return min(1.0, max(values, default=0.0))


def _body_below_score(
    info: _HeaderInfo,
    lines: list[_TextLine],
    following: Optional[_HeaderInfo],
    option_groups: list[Candidate],
    index: _LayoutIndex,
) -> float:
    option_lines = {
        source_id
        for group in option_groups
        for source_id in group.source_element_ids
    }
    candidates: list[_TextLine] = []
    end_order = following.line.order_index if following else math.inf
    for line in lines:
        if not info.line.order_index < line.order_index < end_order:
            continue
        if line.page_index == info.line.page_index and line.bbox.ny0 <= info.line.bbox.ny1:
            continue
        if index.is_noise(line):
            continue
        if all(source_id in option_lines for source_id in line.source_element_ids):
            continue
        if info.line.column_id is not None and line.column_id not in {info.line.column_id, None}:
            continue
        if line.text.strip():
            candidates.append(line)
    return 1.0 if candidates else 0.0


def _alignment_score(info: _HeaderInfo, infos: list[_HeaderInfo], index: _LayoutIndex) -> float:
    values = [
        float(other.line.bbox.nx0)
        for other in infos
        if other is not info and other.line.column_id == info.line.column_id
    ]
    if values:
        return max(0.0, 1.0 - min(1.0, min(abs(info.line.bbox.nx0 - value) for value in values) / 0.12))
    if info.line.column_id is not None:
        return 0.75
    return 0.55


def _style_score(info: _HeaderInfo, infos: list[_HeaderInfo], index: _LayoutIndex) -> float:
    if info.line.style_cluster_id is not None and index.style_frequency(info.line.style_cluster_id) >= 0.015:
        return 1.0
    matching = [
        other
        for other in infos
        if other is not info
        and other.line.bold == info.line.bold
        and abs((other.line.font_size or 0.0) - (info.line.font_size or 0.0)) <= 1.0
    ]
    if matching:
        return 0.8
    return 0.65 if info.line.bold else 0.35


def _line_gaps(info: _HeaderInfo, lines: list[_TextLine], index: _LayoutIndex) -> tuple[float, float]:
    related = [
        line
        for line in lines
        if line.id != info.line.id
        and line.page_index == info.line.page_index
        and line.column_id == info.line.column_id
        and not index.is_noise(line)
    ]
    previous = [line for line in related if line.bbox.ny1 <= info.line.bbox.ny0]
    following = [line for line in related if line.bbox.ny0 >= info.line.bbox.ny1]
    before = (
        max(0.0, info.line.bbox.ny0 - max(line.bbox.ny1 for line in previous))
        / max(index.page_height(info.line.page_index), 1e-9)
        if previous
        else 0.0
    )
    after = (
        max(0.0, min(line.bbox.ny0 for line in following) - info.line.bbox.ny1)
        / max(index.page_height(info.line.page_index), 1e-9)
        if following
        else 0.0
    )
    return before, after


def _sequential_score(prev_delta: int, next_delta: int) -> float:
    if prev_delta == 1 and next_delta == 1:
        return 1.0
    if prev_delta == 1 or next_delta == 1:
        return 0.85
    if prev_delta in {2, 3} or next_delta in {2, 3}:
        return 0.35
    return 0.0


def _same_option_column(first: _TextLine, second: _TextLine, index: _LayoutIndex) -> bool:
    first_column = index.column(first)
    second_column = index.column(second)
    return first_column is None or second_column is None or first_column == second_column


def _normalized_gap(first: _TextLine, second: _TextLine, index: _LayoutIndex) -> float:
    return max(0.0, float(second.bbox.ny0) - float(first.bbox.ny1)) / max(
        index.page_height(first.page_index), 1e-9
    )


def _repeated_option_geometry(group: list[_TextLine], index: _LayoutIndex) -> bool:
    if not group:
        return False
    if any(first.page_index != second.page_index for first, second in zip(group[:-1], group[1:])):
        return False
    if _spread([line.bbox.nx0 for line in group]) > 0.045:
        return False
    gaps = [_normalized_gap(first, second, index) for first, second in zip(group[:-1], group[1:])]
    return not gaps or max(gaps) <= 0.065


def _group_style_similarity(group: list[_TextLine]) -> float:
    if not group:
        return 0.0
    styles = [
        (round(float(line.font_size or 0.0), 1), bool(line.bold), bool(line.italic))
        for line in group
    ]
    return max(styles.count(style) for style in set(styles)) / max(len(styles), 1)


def _nearest_preceding_header(
    line: _TextLine,
    lines: list[_TextLine],
    index: _LayoutIndex,
) -> Optional[_TextLine]:
    candidates = [
        other
        for other in lines
        if other.order_index < line.order_index
        and other.page_index == line.page_index
        and _same_option_column(other, line, index)
        and _parse_header(other, CandidateDetectorConfig()) is not None
    ]
    return max(candidates, key=lambda item: item.order_index, default=None)


def _context_question_numbers(text: str) -> list[int]:
    normalized = _normalize(text)
    if not re.search(r"\bQUESTOES?|ITENS?\b", normalized):
        return []
    numbers = [int(item) for item in re.findall(r"\b\d{1,3}\b", normalized)]
    numbers = [item for item in numbers if 1 <= item <= 200]
    if len(numbers) >= 2 and any(token in normalized for token in (" A ", "-", "ATE")):
        start, end = min(numbers), max(numbers)
        if end - start <= 50:
            return list(range(start, end + 1))
    return list(dict.fromkeys(numbers))


def _line_id_for_source(source_ids: list[str], lines: list[_TextLine]) -> Optional[str]:
    for line in lines:
        if any(source_id in line.source_element_ids for source_id in source_ids):
            return line.id
    return None


def _union_bbox(boxes: list[BBox]) -> Optional[BBox]:
    if not boxes:
        return None
    first = boxes[0]
    return BBox.from_absolute(
        min(item.x0 for item in boxes),
        min(item.y0 for item in boxes),
        max(item.x1 for item in boxes),
        max(item.y1 for item in boxes),
        page_width=max(item.x1 for item in boxes) / max(first.nx1, 1e-9),
        page_height=max(item.y1 for item in boxes) / max(first.ny1, 1e-9),
    )


def _median(values: list[float]) -> Optional[float]:
    return float(statistics.median(values)) if values else None


def _spread(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return max(values) - min(values)


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().upper()
