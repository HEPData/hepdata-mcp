from hepdata_mcp.limits import TruncationPolicy, truncate_value, truncation_metadata


def test_truncate_long_text() -> None:
    policy = TruncationPolicy(max_text_chars=4)

    result = truncate_value("abcdef", policy)

    assert result.truncated is True
    assert result.value == {
        "_truncated": True,
        "original_length": 6,
        "shown_length": 4,
        "value": "abcd",
    }


def test_truncate_long_list() -> None:
    policy = TruncationPolicy(max_list_items=2)

    result = truncate_value([1, 2, 3, 4], policy)

    assert result.truncated is True
    assert result.value == [1, 2, {"_truncated_items": 2}]


def test_truncate_long_dict() -> None:
    policy = TruncationPolicy(max_dict_items=2)

    result = truncate_value({"a": 1, "b": 2, "c": 3}, policy)

    assert result.truncated is True
    assert result.value == {"a": 1, "b": 2, "_truncated_fields": 1}


def test_truncation_metadata_describes_policy() -> None:
    policy = TruncationPolicy(max_text_chars=1, max_list_items=2, max_dict_items=3, max_depth=4)

    assert truncation_metadata(policy) == {
        "truncated": True,
        "max_text_chars": 1,
        "max_list_items": 2,
        "max_dict_items": 3,
        "max_depth": 4,
    }
