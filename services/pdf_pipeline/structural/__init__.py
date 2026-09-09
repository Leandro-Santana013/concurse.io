"""Opt-in structural PDF pipeline components."""

from .model import BBox, DocumentModel, PageModel, PhysicalElement
from .physical import PhysicalExtractor

__all__ = ["BBox", "DocumentModel", "PageModel", "PhysicalElement", "PhysicalExtractor"]
