"""Shared domain data: the ward registry and known emission sources."""

from app.domain.wards import (
    KNOWN_SOURCES,
    WARD_STATE,
    WARD_VULNERABILITY,
    list_ward_ids,
    resolve_ward_id,
    sources_for_ward,
    ward_row,
    ward_vulnerability_row,
)

__all__ = [
    "KNOWN_SOURCES",
    "WARD_STATE",
    "WARD_VULNERABILITY",
    "list_ward_ids",
    "resolve_ward_id",
    "sources_for_ward",
    "ward_row",
    "ward_vulnerability_row",
]
