"""Question-region delimitation and geometry-first image ownership."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Optional

from ...media.diagram_cropper import IMAGE_TRIGGER_REGEX
from ..layout.models import ElementLayout, LayoutAnalysis
from ..model import BBox, DocumentModel, PhysicalElement
from .config import RegionConfig
from .graph import DocumentGraph, EdgeType, GraphNode
from .models import (
    Candidate,
    CandidateDetection,
    ContextBlock,
    ImageOwnership,
    PageSegment,
    QuestionRegion,
)


class QuestionRegionBuilder:
    """Build preliminary regions between consecutive header candidates.

    The builder does not solve the final question sequence. It consumes the
    current structural reading order and keeps every cross-page segment
    explicit, so later phases can revise ownership without re-extracting PDF
    elements.
    """

    def __init__(self, config: Optional[RegionConfig] = None) -> None:
        self.config = config or RegionConfig()
        self.last_image_ownership: list[ImageOwnership] = []
        self.last_context_blocks: list[ContextBlock] = []

    def build(
        self,
        document: DocumentModel,
        layout_analysis: LayoutAnalysis,
        detection: CandidateDetection,
        graph: DocumentGraph,
    ) -> list[QuestionRegion]:
        physical = {
            element.id: element
            for page in document.pages
            for element in page.elements
        }
        element_layout = {
            item.element_id: item
            for page in layout_analysis.pages
            for item in page.elements
        }
        roles = layout_analysis.zones.element_roles
        sequence = self._document_sequence(document, layout_analysis, physical)
        order = {element_id: position for position, element_id in enumerate(sequence)}
        headers = sorted(
            detection.question_headers,
            key=lambda item: (
                min((order.get(element_id, 10**9) for element_id in item.source_element_ids), default=10**9),
                item.id,
            ),
        )
        if not headers:
            self.last_image_ownership = []
            self.last_context_blocks = self._context_blocks(detection, headers)
            return []

        regions: list[QuestionRegion] = []
        for position, header in enumerate(headers):
            start = min((order.get(element_id, 10**9) for element_id in header.source_element_ids), default=0)
            end = (
                min(
                    (order.get(element_id, 10**9) for element_id in headers[position + 1].source_element_ids),
                    default=len(sequence),
                )
                if position + 1 < len(headers)
                else len(sequence)
            )
            if end < start:
                end = start
            raw_ids = sequence[start:end]
            # Keep the header even if it was a zero-width or missing reading
            # link in a synthetic/partial model.
            for element_id in header.source_element_ids:
                if element_id in physical and element_id not in raw_ids:
                    raw_ids.insert(0, element_id)
            content_ids = [
                element_id
                for element_id in raw_ids
                if element_id in physical
                and not (
                    element_id not in header.source_element_ids
                    and
                    self.config.exclude_header_footer_noise
                    and any(
                        role in {"HEADER_NOISE", "FOOTER_NOISE"}
                        for role in roles.get(element_id, [])
                    )
                )
            ]
            segments = self._segments(content_ids, order, physical, document)
            option_ids = [
                candidate.id
                for candidate in detection.option_groups
                if _intersects(candidate.source_element_ids, set(content_ids))
            ]
            context_ids = [
                candidate.id
                for candidate in detection.contexts
                if _intersects(candidate.source_element_ids, set(content_ids))
                or int(header.metadata.get("question_number", -1))
                in [int(number) for number in candidate.metadata.get("question_numbers", [])]
            ]
            regions.append(
                QuestionRegion(
                    id=f"question-region:{header.id}",
                    question_candidate_id=header.id,
                    question_number=(
                        int(header.metadata["question_number"])
                        if header.metadata.get("question_number") is not None
                        else None
                    ),
                    segments=segments,
                    content_element_ids=content_ids,
                    option_candidate_ids=option_ids,
                    context_candidate_ids=context_ids,
                    metadata={
                        "start_order": start,
                        "end_order": end,
                        "cross_page": len({physical[item].page_index for item in content_ids}) > 1,
                    },
                )
            )

        ownership = self._assign_images(
            document,
            layout_analysis,
            regions,
            headers,
            sequence,
            order,
            physical,
            element_layout,
            roles,
        )
        self.last_image_ownership = ownership
        self.last_context_blocks = self._context_blocks(detection, headers)
        self._add_graph_nodes_and_edges(
            graph,
            regions,
            ownership,
            detection,
            self.last_context_blocks,
        )
        return regions

    def _document_sequence(
        self,
        document: DocumentModel,
        layout_analysis: LayoutAnalysis,
        physical: Mapping[str, PhysicalElement],
    ) -> list[str]:
        result: list[str] = []
        for page in sorted(layout_analysis.pages, key=lambda item: item.page_index):
            result.extend(
                element_id
                for element_id in page.reading_order.sequence
                if element_id in physical
            )
        known = set(result)
        result.extend(
            element.id
            for page in sorted(document.pages, key=lambda item: item.page_index)
            for element in sorted(page.elements, key=lambda item: (item.bbox.ny0, item.bbox.nx0, item.id))
            if element.id not in known
        )
        return result

    def _segments(
        self,
        element_ids: list[str],
        order: Mapping[str, int],
        physical: Mapping[str, PhysicalElement],
        document: DocumentModel,
    ) -> list[PageSegment]:
        by_page: dict[int, list[str]] = defaultdict(list)
        for element_id in element_ids:
            by_page[physical[element_id].page_index].append(element_id)
        segments: list[PageSegment] = []
        for page_index in sorted(by_page):
            page_ids = sorted(by_page[page_index], key=lambda item: order.get(item, 10**9))
            segments.append(
                PageSegment(
                    page_index=page_index,
                    element_ids=page_ids,
                    bbox=_union_physical_bbox(page_ids, physical, document),
                    start_order=min((order.get(item, 10**9) for item in page_ids), default=None),
                    end_order=max((order.get(item, -1) for item in page_ids), default=None),
                )
            )
        return segments

    def _assign_images(
        self,
        document: DocumentModel,
        layout_analysis: LayoutAnalysis,
        regions: list[QuestionRegion],
        headers: list[Candidate],
        sequence: list[str],
        order: Mapping[str, int],
        physical: Mapping[str, PhysicalElement],
        element_layout: Mapping[str, ElementLayout],
        roles: Mapping[str, list[str]],
    ) -> list[ImageOwnership]:
        visuals = [
            element
            for element in physical.values()
            if element.kind in {"image", "drawing"}
        ]
        ownership: list[ImageOwnership] = []
        header_by_region = {
            region.id: next(
                (candidate for candidate in headers if candidate.id == region.question_candidate_id),
                None,
            )
            for region in regions
        }
        for image in visuals:
            scored: list[tuple[float, ImageOwnership, QuestionRegion]] = []
            for region in regions:
                header = header_by_region.get(region.id)
                if header is None:
                    continue
                evidence = self._image_evidence(
                    image,
                    region,
                    header,
                    headers,
                    order,
                    physical,
                    element_layout,
                    roles,
                )
                score = (
                    self.config.inside_region_weight * evidence["inside_question_region"]
                    + self.config.same_column_weight * evidence["same_column"]
                    + self.config.nearest_statement_weight * evidence["nearest_statement"]
                    + self.config.trigger_word_weight * evidence["trigger_word_nearby"]
                    - self.config.crossing_next_question_penalty * evidence["crossing_next_question_penalty"]
                    - self.config.header_footer_penalty * evidence["header_footer_penalty"]
                )
                scored.append(
                    (
                        score,
                        ImageOwnership(
                            image_element_id=image.id,
                            question_candidate_id=header.id,
                            score=round(score, 8),
                            evidence=evidence,
                            metadata={
                                "page_index": image.page_index,
                                "geometry_first": True,
                                "trigger_optional": True,
                            },
                        ),
                        region,
                    )
                )
            if not scored:
                continue
            best_score, best, region = max(scored, key=lambda item: (item[0], -int(item[2].metadata.get("start_order", 0))))
            if best_score < self.config.min_image_ownership_score:
                continue
            best.score = round(best_score, 8)
            ownership.append(best)
            region.image_element_ids.append(image.id)
            region.image_ownership.append(best)
        return ownership

    def _image_evidence(
        self,
        image: PhysicalElement,
        region: QuestionRegion,
        header: Candidate,
        headers: list[Candidate],
        order: Mapping[str, int],
        physical: Mapping[str, PhysicalElement],
        element_layout: Mapping[str, ElementLayout],
        roles: Mapping[str, list[str]],
    ) -> dict[str, float]:
        content_ids = set(region.content_element_ids)
        inside = float(image.id in content_ids)
        image_layout = element_layout.get(image.id)
        header_columns = {
            element_layout[element_id].column_id
            for element_id in header.source_element_ids
            if element_id in element_layout and element_layout[element_id].column_id is not None
        }
        same_column = 0.5
        if image_layout and image_layout.column_id is not None and header_columns:
            same_column = float(image_layout.column_id in header_columns)
        elif image.page_index != header.page_index:
            same_column = 0.0
        statements = [
            element
            for element_id, element in physical.items()
            if element_id in content_ids
            and element.kind == "text"
            and element_id not in header.source_element_ids
        ]
        nearest = _nearest_geometry_score(image, statements)
        trigger = 0.0
        for element in statements:
            if element.page_index != image.page_index:
                continue
            if IMAGE_TRIGGER_REGEX.search(str(element.text or "")):
                y_distance = abs(
                    (float(element.bbox.ny0) + float(element.bbox.ny1)) / 2.0
                    - (float(image.bbox.ny0) + float(image.bbox.ny1)) / 2.0
                )
                if y_distance <= 0.35:
                    trigger = 1.0
                    break
        next_headers = [candidate for candidate in headers if candidate.id != header.id]
        current_order = order.get(image.id, 10**9)
        next_order = min(
            (
                min((order.get(element_id, 10**9) for element_id in candidate.source_element_ids), default=10**9)
                for candidate in next_headers
                if min((order.get(element_id, 10**9) for element_id in candidate.source_element_ids), default=10**9)
                > order.get(header.source_element_ids[0], -1)
            ),
            default=10**9,
        )
        crossing = float(current_order >= next_order)
        noise = float(
            any(role in {"HEADER_NOISE", "FOOTER_NOISE"} for role in roles.get(image.id, []))
        )
        return {
            "inside_question_region": inside,
            "same_column": same_column,
            "nearest_statement": nearest,
            "trigger_word_nearby": trigger,
            "crossing_next_question_penalty": crossing,
            "header_footer_penalty": noise,
        }

    def _context_blocks(
        self,
        detection: CandidateDetection,
        headers: list[Candidate],
    ) -> list[ContextBlock]:
        blocks: list[ContextBlock] = []
        for candidate in detection.contexts:
            numbers = [int(item) for item in candidate.metadata.get("question_numbers", [])]
            applied = [
                header.id
                for header in headers
                if header.metadata.get("question_number") in numbers
            ]
            blocks.append(
                ContextBlock(
                    id=candidate.id,
                    source_element_ids=list(candidate.source_element_ids),
                    applies_to_candidate_ids=applied,
                    question_numbers=numbers,
                    text=str(candidate.metadata.get("text", "")),
                    score=candidate.score,
                    evidence=dict(candidate.evidence),
                )
            )
        return blocks

    def _add_graph_nodes_and_edges(
        self,
        graph: DocumentGraph,
        regions: list[QuestionRegion],
        ownership: list[ImageOwnership],
        detection: CandidateDetection,
        context_blocks: list[ContextBlock],
    ) -> None:
        for region in regions:
            graph.add_node(
                GraphNode(
                    id=region.id,
                    kind="QUESTION_REGION",
                    page_index=region.segments[0].page_index if region.segments else None,
                    bbox=region.segments[0].bbox if region.segments else None,
                    data={"region": region.to_dict()},
                )
            )
            graph.add_edge(region.id, region.question_candidate_id, EdgeType.CONTAINS)
            for element_id in region.content_element_ids:
                graph.add_edge(region.id, element_id, EdgeType.CONTAINS)
            for option_id in region.option_candidate_ids:
                graph.add_edge(region.id, option_id, EdgeType.CONTAINS)
        for item in ownership:
            region = next(
                (region for region in regions if region.question_candidate_id == item.question_candidate_id),
                None,
            )
            if region is None:
                continue
            graph.add_edge(
                region.id,
                item.image_element_id,
                EdgeType.OWNS_IMAGE,
                weight=item.score,
                evidence=item.evidence,
            )
        for block in context_blocks:
            for candidate_id in block.applies_to_candidate_ids:
                graph.add_edge(
                    block.id,
                    candidate_id,
                    EdgeType.APPLIES_TO,
                    weight=block.score,
                    metadata={"shared_context": True},
                )


def _intersects(first: list[str], second: set[str]) -> bool:
    return any(item in second for item in first)


def _nearest_geometry_score(image: PhysicalElement, statements: list[PhysicalElement]) -> float:
    if not statements:
        return 0.0
    image_x = (float(image.bbox.nx0) + float(image.bbox.nx1)) / 2.0
    image_y = (float(image.bbox.ny0) + float(image.bbox.ny1)) / 2.0
    distance = min(
        (
            ((image_x - (float(item.bbox.nx0) + float(item.bbox.nx1)) / 2.0) ** 2)
            + ((image_y - (float(item.bbox.ny0) + float(item.bbox.ny1)) / 2.0) ** 2)
        ) ** 0.5
        for item in statements
    )
    return max(0.0, 1.0 - min(1.0, distance / 0.45))


def _union_physical_bbox(
    element_ids: list[str],
    physical: Mapping[str, PhysicalElement],
    document: DocumentModel,
) -> Optional[BBox]:
    boxes = [physical[item].bbox for item in element_ids if item in physical]
    if not boxes:
        return None
    page_index = physical[element_ids[0]].page_index
    page = document.pages[page_index]
    return BBox.from_absolute(
        min(item.x0 for item in boxes),
        min(item.y0 for item in boxes),
        max(item.x1 for item in boxes),
        max(item.y1 for item in boxes),
        page.width,
        page.height,
    )
