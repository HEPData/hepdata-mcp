"""Response shaping helpers for MCP-facing payloads."""

from dataclasses import dataclass
from typing import Any

DEFAULT_MAX_TEXT_CHARS = 20_000
DEFAULT_MAX_LIST_ITEMS = 200
DEFAULT_MAX_DICT_ITEMS = 200
DEFAULT_MAX_DEPTH = 12


@dataclass(frozen=True)
class TruncationPolicy:
    """Limits applied to values before returning them through MCP tools."""

    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS
    max_list_items: int = DEFAULT_MAX_LIST_ITEMS
    max_dict_items: int = DEFAULT_MAX_DICT_ITEMS
    max_depth: int = DEFAULT_MAX_DEPTH


@dataclass(frozen=True)
class TruncationResult:
    """A value after applying a truncation policy."""

    value: Any
    truncated: bool


DEFAULT_TRUNCATION_POLICY = TruncationPolicy()


def truncate_value(
    value: Any,
    policy: TruncationPolicy = DEFAULT_TRUNCATION_POLICY,
) -> TruncationResult:
    """Return a JSON-like value bounded by the provided policy."""
    truncated_value, truncated = _truncate_value(value, policy, depth=0)
    return TruncationResult(value=truncated_value, truncated=truncated)


def truncation_metadata(
    policy: TruncationPolicy = DEFAULT_TRUNCATION_POLICY,
) -> dict[str, int | bool]:
    """Return metadata describing the default truncation policy."""
    return {
        "truncated": True,
        "max_text_chars": policy.max_text_chars,
        "max_list_items": policy.max_list_items,
        "max_dict_items": policy.max_dict_items,
        "max_depth": policy.max_depth,
    }


def _truncate_value(value: Any, policy: TruncationPolicy, *, depth: int) -> tuple[Any, bool]:
    if depth >= policy.max_depth:
        return {"_truncated": True, "reason": "maximum nesting depth reached"}, True

    if isinstance(value, str):
        if len(value) <= policy.max_text_chars:
            return value, False
        return (
            {
                "_truncated": True,
                "original_length": len(value),
                "shown_length": policy.max_text_chars,
                "value": value[: policy.max_text_chars],
            },
            True,
        )

    if isinstance(value, list):
        shown_items = value[: policy.max_list_items]
        truncated_items = len(value) - len(shown_items)
        child_list: list[Any] = []
        child_truncated = truncated_items > 0
        for item in shown_items:
            truncated_item, item_was_truncated = _truncate_value(item, policy, depth=depth + 1)
            child_list.append(truncated_item)
            child_truncated = child_truncated or item_was_truncated
        if truncated_items > 0:
            child_list.append({"_truncated_items": truncated_items})
        return child_list, child_truncated

    if isinstance(value, dict):
        shown_entries = list(value.items())[: policy.max_dict_items]
        truncated_entries = len(value) - len(shown_entries)
        child_dict: dict[str, Any] = {}
        child_truncated = truncated_entries > 0
        for key, item in shown_entries:
            truncated_item, item_was_truncated = _truncate_value(item, policy, depth=depth + 1)
            child_dict[str(key)] = truncated_item
            child_truncated = child_truncated or item_was_truncated
        if truncated_entries > 0:
            child_dict["_truncated_fields"] = truncated_entries
        return child_dict, child_truncated

    return value, False
