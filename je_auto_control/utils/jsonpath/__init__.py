"""Minimal JSONPath-style querying over parsed JSON data."""
from je_auto_control.utils.jsonpath.jsonpath import (
    json_extract, json_query, json_query_one,
)

__all__ = ["json_extract", "json_query", "json_query_one"]
