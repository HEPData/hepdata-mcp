import pytest

from hepdata_mcp.errors import HEPDataFormatError, HEPDataIdentifierError
from hepdata_mcp.identifiers import (
    normalize_record_identifier,
    validate_record_export_format,
    validate_table_format,
)


def test_normalize_inspire_record_identifier() -> None:
    identifier = normalize_record_identifier(" ins3103133 ")

    assert identifier.value == "ins3103133"
    assert identifier.path_segment == "ins3103133"


def test_normalize_hepdata_record_url() -> None:
    identifier = normalize_record_identifier("https://www.hepdata.net/record/ins3103133")

    assert identifier.value == "ins3103133"


def test_normalize_hepdata_doi_to_record_id() -> None:
    identifier = normalize_record_identifier("https://doi.org/10.17182/hepdata.167818.v1")

    assert identifier.value == "167818"


def test_reject_identifier_with_path_syntax() -> None:
    with pytest.raises(HEPDataIdentifierError):
        normalize_record_identifier("not/a/record")


def test_reject_identifier_with_control_or_whitespace_characters() -> None:
    with pytest.raises(HEPDataIdentifierError):
        normalize_record_identifier("ins\n3103133")

    with pytest.raises(HEPDataIdentifierError):
        normalize_record_identifier("ins 3103133")


def test_reject_overlong_identifier() -> None:
    with pytest.raises(HEPDataIdentifierError):
        normalize_record_identifier("i" * 101)


def test_validate_formats() -> None:
    assert validate_record_export_format("yoda.h5") == "yoda.h5"
    assert validate_table_format("csv") == "csv"


def test_reject_unknown_formats() -> None:
    with pytest.raises(HEPDataFormatError):
        validate_record_export_format("parquet")

    with pytest.raises(HEPDataFormatError):
        validate_table_format("root")
