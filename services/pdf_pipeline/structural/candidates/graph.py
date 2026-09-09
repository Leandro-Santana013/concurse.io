"""Sparse, serializable document graph for physical and candidate evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Iterable, Iterator, Mapping, Optional

from ..layout.models import LayoutAnalysis
from ..model import BBox, DocumentModel, PhysicalElement
from .config import GraphConfig
from .models import Candidate, CandidateDetection


class EdgeType(str, Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    LEFT_OF = "LEFT_OF"
    RIGHT_OF = "RIGHT_OF"
    SAME_COLUMN = "SAME_COLUMN"
    SAME_LINE = "SAME_LINE"
    ALIGNED_LEFT = "ALIGNED_LEFT"
    ALIGNED_CENTER = "ALIGNED_CENTER"
    NEAR = "NEAR"
    CONTAINS = "CONTAINS"
    OVERLAPS = "OVERLAPS"
    SAME_STYLE_CLUSTER = "SAME_STYLE_CLUSTER"
    NEXT_READING_BLOCK = "NEXT_READING_BLOCK"
    APPLIES_TO = "APPLIES_TO"
    OWNS_IMAGE = "OWNS_IMAGE"


@dataclass
class GraphNode:
    id: str
    kind: str
    page_index: Optional[int] = None
    bbox: Optional[BBox] = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def node_id(self) -> str:
        return self.id

    @property
    def node_type(self) -> str:
        return self.kind

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "page_index": self.page_index,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphNode":
        return cls(
            id=str(value["id"]),
            kind=str(value["kind"]),
            page_index=(int(value["page_index"]) if value.get("page_index") is not None else None),
            bbox=BBox.from_dict(value["bbox"]) if value.get("bbox") else None,
            data=dict(value.get("data") or {}),
        )


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0
    evidence: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def edge_type(self) -> str:
        return self.relation

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "weight": float(self.weight),
            "evidence": dict(sorted(self.evidence.items())),
            "metadata": self.metadata,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphEdge":
        return cls(
            source=str(value["source"]),
            target=str(value["target"]),
            relation=str(value["relation"]),
            weight=float(value.get("weight", 1.0)),
            evidence={str(k): float(v) for k, v in (value.get("evidence") or {}).items()},
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass
class DocumentGraph:
    """Adjacency-list graph; edge insertion is deduplicated and inspectable."""

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges_by_source: dict[str, list[GraphEdge]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _edge_keys: set[tuple[str, str, str]] = field(default_factory=set, repr=False)

    def add_node(self, node: GraphNode) -> GraphNode:
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return node
        if node.data:
            existing.data.update(node.data)
        return existing

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str | EdgeType,
        *,
        weight: float = 1.0,
        evidence: Optional[Mapping[str, float]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Optional[GraphEdge]:
        if source == target or source not in self.nodes or target not in self.nodes:
            return None
        relation_value = relation.value if isinstance(relation, EdgeType) else str(relation)
        key = (str(source), str(target), relation_value)
        if key in self._edge_keys:
            return None
        edge = GraphEdge(
            source=str(source),
            target=str(target),
            relation=relation_value,
            weight=float(weight),
            evidence={str(k): float(v) for k, v in (evidence or {}).items()},
            metadata=dict(metadata or {}),
        )
        self._edge_keys.add(key)
        self.edges_by_source.setdefault(edge.source, []).append(edge)
        return edge

    def edges(self) -> Iterator[GraphEdge]:
        for source in sorted(self.edges_by_source):
            yield from sorted(
                self.edges_by_source[source],
                key=lambda edge: (edge.relation, edge.target),
            )

    def neighbors(self, source: str, relation: Optional[str] = None) -> list[str]:
        return [
            edge.target
            for edge in self.edges_by_source.get(source, [])
            if relation is None or edge.relation == str(relation)
        ]

    def stats(self) -> dict[str, Any]:
        relation_counts: dict[str, int] = defaultdict(int)
        node_counts: dict[str, int] = defaultdict(int)
        edge_count = 0
        for node in self.nodes.values():
            node_counts[node.kind] += 1
        for edge in self.edges():
            relation_counts[edge.relation] += 1
            edge_count += 1
        node_count = len(self.nodes)
        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "node_types": dict(sorted(node_counts.items())),
            "edge_types": dict(sorted(relation_counts.items())),
            "sparse_upper_bound": node_count * max(node_count - 1, 0),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "nodes": [self.nodes[key].to_dict() for key in sorted(self.nodes)],
            "edges": [edge.to_dict() for edge in self.edges()],
            "stats": self.stats(),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DocumentGraph":
        graph = cls()
        for item in value.get("nodes", []):
            graph.add_node(GraphNode.from_dict(item))
        for item in value.get("edges", []):
            edge = GraphEdge.from_dict(item)
            graph.add_edge(
                edge.source,
                edge.target,
                edge.relation,
                weight=edge.weight,
                evidence=edge.evidence,
                metadata=edge.metadata,
            )
        return graph


class DocumentGraphBuilder:
    """Build local spatial/reading relationships without an N² pass."""

    def __init__(self, config: Optional[GraphConfig] = None) -> None:
        self.config = config or GraphConfig()

    def build(
        self,
        document: DocumentModel,
        layout_analysis: LayoutAnalysis,
        detection: CandidateDetection,
    ) -> DocumentGraph:
        graph = DocumentGraph()
        physical = {
            element.id: element
            for page in document.pages
            for element in page.elements
        }
        layout_by_id = {
            item.element_id: item
            for page in layout_analysis.pages
            for item in page.elements
        }
        for element in physical.values():
            graph.add_node(
                GraphNode(
                    id=element.id,
                    kind="ELEMENT",
                    page_index=element.page_index,
                    bbox=element.bbox,
                    data={
                        "element_kind": element.kind,
                        "text": element.text,
                        "source": element.source,
                    },
                )
            )

        candidates = detection.candidates
        candidate_by_id = {candidate.id: candidate for candidate in candidates}
        for candidate in candidates:
            graph.add_node(
                GraphNode(
                    id=candidate.id,
                    kind=candidate.type,
                    page_index=candidate.page_index,
                    bbox=candidate.bbox,
                    data={"candidate": candidate.to_dict()},
                )
            )
            for element_id in candidate.source_element_ids:
                if element_id in physical:
                    graph.add_edge(
                        candidate.id,
                        element_id,
                        EdgeType.CONTAINS,
                        weight=max(0.01, candidate.score),
                        metadata={"role": "candidate_source"},
                    )

        self._reading_edges(graph, layout_analysis)
        self._local_page_edges(graph, document, layout_by_id, physical)
        self._candidate_edges(graph, detection, physical, layout_by_id)
        self._context_edges(graph, detection)
        return graph

    def _reading_edges(self, graph: DocumentGraph, layout_analysis: LayoutAnalysis) -> None:
        for page in layout_analysis.pages:
            for source, target in page.reading_order.next_reading_block.items():
                if target is not None:
                    graph.add_edge(
                        source,
                        target,
                        EdgeType.NEXT_READING_BLOCK,
                        metadata={"page_index": page.page_index},
                    )

    def _local_page_edges(
        self,
        graph: DocumentGraph,
        document: DocumentModel,
        layout_by_id: Mapping[str, Any],
        physical: Mapping[str, PhysicalElement],
    ) -> None:
        for page in document.pages:
            elements = [element for element in page.elements if element.id in graph.nodes]
            if not elements:
                continue
            ordered = sorted(
                elements,
                key=lambda element: (
                    int(layout_by_id[element.id].order_index)
                    if layout_by_id.get(element.id) is not None
                    and layout_by_id[element.id].order_index is not None
                    else float(element.bbox.ny0),
                    float(element.bbox.nx0),
                    element.id,
                ),
            )
            self._adjacent_vertical_edges(graph, ordered, layout_by_id)
            self._line_edges(graph, ordered, layout_by_id)
            self._style_edges(graph, ordered, layout_by_id)
            self._alignment_edges(graph, ordered, layout_by_id)
            self._spatial_edges(graph, page.width, page.height, ordered)

    def _adjacent_vertical_edges(
        self,
        graph: DocumentGraph,
        ordered: list[PhysicalElement],
        layout_by_id: Mapping[str, Any],
    ) -> None:
        by_column: dict[Optional[int], list[PhysicalElement]] = defaultdict(list)
        for element in ordered:
            layout = layout_by_id.get(element.id)
            by_column[layout.column_id if layout else None].append(element)
        for column_elements in by_column.values():
            column_elements.sort(key=lambda item: (item.bbox.ny0, item.bbox.nx0, item.id))
            for upper, lower in zip(column_elements[:-1], column_elements[1:]):
                graph.add_edge(upper.id, lower.id, EdgeType.BELOW)
                graph.add_edge(lower.id, upper.id, EdgeType.ABOVE)
                if layout_by_id.get(upper.id) and layout_by_id.get(lower.id):
                    graph.add_edge(upper.id, lower.id, EdgeType.SAME_COLUMN)
                    graph.add_edge(lower.id, upper.id, EdgeType.SAME_COLUMN)

    def _line_edges(
        self,
        graph: DocumentGraph,
        ordered: list[PhysicalElement],
        layout_by_id: Mapping[str, Any],
    ) -> None:
        lines: dict[tuple[Any, ...], list[PhysicalElement]] = defaultdict(list)
        for element in ordered:
            metadata = element.metadata or {}
            if metadata.get("block_index") is not None and metadata.get("line_index") is not None:
                key = ("native", metadata.get("block_index"), metadata.get("line_index"))
            else:
                layout = layout_by_id.get(element.id)
                column = layout.column_id if layout else None
                key = ("geometry", column, round(float(element.bbox.ny0) / 0.006))
            lines[key].append(element)
        for line in lines.values():
            line.sort(key=lambda item: (item.bbox.nx0, item.id))
            for left, right in zip(line[:-1], line[1:]):
                graph.add_edge(left.id, right.id, EdgeType.RIGHT_OF)
                graph.add_edge(right.id, left.id, EdgeType.LEFT_OF)
                graph.add_edge(left.id, right.id, EdgeType.SAME_LINE)
                graph.add_edge(right.id, left.id, EdgeType.SAME_LINE)

    def _style_edges(
        self,
        graph: DocumentGraph,
        ordered: list[PhysicalElement],
        layout_by_id: Mapping[str, Any],
    ) -> None:
        groups: dict[tuple[int, int], list[PhysicalElement]] = defaultdict(list)
        for element in ordered:
            layout = layout_by_id.get(element.id)
            if layout and layout.style_cluster_id is not None:
                groups[(element.page_index, int(layout.style_cluster_id))].append(element)
        for group in groups.values():
            group.sort(key=lambda item: (item.bbox.ny0, item.bbox.nx0, item.id))
            for first, second in zip(group[:-1], group[1:]):
                graph.add_edge(first.id, second.id, EdgeType.SAME_STYLE_CLUSTER)
                graph.add_edge(second.id, first.id, EdgeType.SAME_STYLE_CLUSTER)

    def _alignment_edges(
        self,
        graph: DocumentGraph,
        ordered: list[PhysicalElement],
        layout_by_id: Mapping[str, Any],
    ) -> None:
        for attribute, relation in (
            ("nx0", EdgeType.ALIGNED_LEFT),
            ("center", EdgeType.ALIGNED_CENTER),
        ):
            buckets: dict[int, list[PhysicalElement]] = defaultdict(list)
            for element in ordered:
                value = (
                    float(element.bbox.nx0)
                    if attribute == "nx0"
                    else (float(element.bbox.nx0) + float(element.bbox.nx1)) / 2.0
                )
                buckets[round(value / 0.025)].append(element)
            for group in buckets.values():
                group.sort(key=lambda item: (item.bbox.ny0, item.id))
                for first, second in zip(group[: self.config.max_alignment_neighbors], group[1:]):
                    graph.add_edge(first.id, second.id, relation)
                    graph.add_edge(second.id, first.id, relation)

    def _spatial_edges(
        self,
        graph: DocumentGraph,
        page_width: float,
        page_height: float,
        elements: list[PhysicalElement],
    ) -> None:
        grid = max(4, int(self.config.spatial_grid_size))
        buckets: dict[tuple[int, int], list[PhysicalElement]] = defaultdict(list)
        for element in elements:
            x0 = max(0, min(grid - 1, int(float(element.bbox.nx0) * grid)))
            x1 = max(0, min(grid - 1, int(float(element.bbox.nx1) * grid)))
            y0 = max(0, min(grid - 1, int(float(element.bbox.ny0) * grid)))
            y1 = max(0, min(grid - 1, int(float(element.bbox.ny1) * grid)))
            for x in range(x0, min(x1, x0 + 2) + 1):
                for y in range(y0, min(y1, y0 + 2) + 1):
                    buckets[(x, y)].append(element)

        seen: set[tuple[str, str]] = set()
        for bucket_elements in buckets.values():
            ordered = sorted(bucket_elements, key=lambda item: (item.bbox.nx0, item.bbox.ny0, item.id))
            for index, first in enumerate(ordered):
                for second in ordered[index + 1 : index + 1 + self.config.max_neighbors_per_bucket]:
                    pair = (first.id, second.id) if first.id < second.id else (second.id, first.id)
                    if pair in seen:
                        continue
                    seen.add(pair)
                    self._pair_edges(graph, first, second, page_width, page_height)

    def _pair_edges(
        self,
        graph: DocumentGraph,
        first: PhysicalElement,
        second: PhysicalElement,
        page_width: float,
        page_height: float,
    ) -> None:
        horizontal_gap = max(
            0.0,
            max(float(first.bbox.nx0), float(second.bbox.nx0))
            - min(float(first.bbox.nx1), float(second.bbox.nx1)),
        )
        vertical_gap = max(
            0.0,
            max(float(first.bbox.ny0), float(second.bbox.ny0))
            - min(float(first.bbox.ny1), float(second.bbox.ny1)),
        )
        center_distance = (
            ((float(first.bbox.nx0) + float(first.bbox.nx1)) / 2.0 - (float(second.bbox.nx0) + float(second.bbox.nx1)) / 2.0) ** 2
            + ((float(first.bbox.ny0) + float(first.bbox.ny1)) / 2.0 - (float(second.bbox.ny0) + float(second.bbox.ny1)) / 2.0) ** 2
        ) ** 0.5
        if center_distance <= self.config.near_radius_norm:
            graph.add_edge(first.id, second.id, EdgeType.NEAR, weight=max(0.0, 1.0 - center_distance))
            graph.add_edge(second.id, first.id, EdgeType.NEAR, weight=max(0.0, 1.0 - center_distance))

        overlap_x = min(first.bbox.nx1, second.bbox.nx1) - max(first.bbox.nx0, second.bbox.nx0)
        overlap_y = min(first.bbox.ny1, second.bbox.ny1) - max(first.bbox.ny0, second.bbox.ny0)
        if overlap_x > 0.0 and overlap_y > 0.0:
            graph.add_edge(first.id, second.id, EdgeType.OVERLAPS)
            graph.add_edge(second.id, first.id, EdgeType.OVERLAPS)
        if _contains(first.bbox, second.bbox):
            graph.add_edge(first.id, second.id, EdgeType.CONTAINS)
        elif _contains(second.bbox, first.bbox):
            graph.add_edge(second.id, first.id, EdgeType.CONTAINS)

    def _candidate_edges(
        self,
        graph: DocumentGraph,
        detection: CandidateDetection,
        physical: Mapping[str, PhysicalElement],
        layout_by_id: Mapping[str, Any],
    ) -> None:
        for header in detection.question_headers:
            header_column = _candidate_column(header, layout_by_id)
            for option in detection.option_groups:
                if not _candidate_is_below(header, option):
                    continue
                option_column = _candidate_column(option, layout_by_id)
                if header_column is None or option_column is None or header_column == option_column:
                    graph.add_edge(
                        header.id,
                        option.id,
                        EdgeType.BELOW,
                        weight=option.score,
                        metadata={"role": "option_group_below"},
                    )
                    if header_column is not None and header_column == option_column:
                        graph.add_edge(header.id, option.id, EdgeType.SAME_COLUMN)

    def _context_edges(self, graph: DocumentGraph, detection: CandidateDetection) -> None:
        headers_by_number = {
            int(candidate.metadata["question_number"]): candidate
            for candidate in detection.question_headers
            if candidate.metadata.get("question_number") is not None
        }
        for context in detection.contexts:
            for number in context.metadata.get("question_numbers", []):
                header = headers_by_number.get(int(number))
                if header is not None:
                    graph.add_edge(
                        context.id,
                        header.id,
                        EdgeType.APPLIES_TO,
                        weight=context.score,
                        metadata={"question_number": int(number)},
                    )


def _contains(first: BBox, second: BBox) -> bool:
    return (
        first.nx0 <= second.nx0
        and first.ny0 <= second.ny0
        and first.nx1 >= second.nx1
        and first.ny1 >= second.ny1
        and (
            first.nx0 < second.nx0
            or first.ny0 < second.ny0
            or first.nx1 > second.nx1
            or first.ny1 > second.ny1
        )
    )


def _candidate_column(candidate: Candidate, layout_by_id: Mapping[str, Any]) -> Optional[int]:
    columns = {
        layout_by_id[element_id].column_id
        for element_id in candidate.source_element_ids
        if element_id in layout_by_id and layout_by_id[element_id].column_id is not None
    }
    return next(iter(columns)) if len(columns) == 1 else None


def _candidate_is_below(first: Candidate, second: Candidate) -> bool:
    if first.page_index is None or second.page_index is None:
        return False
    if second.page_index > first.page_index:
        return True
    if second.page_index < first.page_index:
        return False
    return float(second.bbox.ny0 if second.bbox else 0.0) > float(first.bbox.ny1 if first.bbox else 0.0)
