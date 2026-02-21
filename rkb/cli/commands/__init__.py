"""CLI command modules for the RKB system."""

# Import all command modules for easy access
from . import (
    documents_cmd,
    enrich_cmd,
    index_cmd,
    ingest_cmd,
    rectify_cmd,
    remove_cmd,
    search_cmd,
    status_cmd,
    translate_cmd,
    triage_cmd,
)

__all__ = [
    "documents_cmd",
    "enrich_cmd",
    "index_cmd",
    "ingest_cmd",
    "rectify_cmd",
    "remove_cmd",
    "search_cmd",
    "status_cmd",
    "translate_cmd",
    "triage_cmd",
]
