from datetime import datetime

import pytest

from app.filters import FilterParseError, parse_sys_updated_on_filters


def test_parse_single_filter_ok() -> None:
    predicates = parse_sys_updated_on_filters("sys_updated_on.gte.2021-08-03+14:09:24")
    assert len(predicates) == 1
    assert predicates[0](datetime(2021, 8, 3, 14, 9, 24)) is True
    assert predicates[0](datetime(2021, 8, 3, 14, 9, 23)) is False


def test_parse_multiple_filters_ok() -> None:
    predicates = parse_sys_updated_on_filters(
        "sys_updated_on.gte.2021-08-03+14:09:24&sys_updated_on.lt.2021-08-04+00:00:00"
    )
    assert len(predicates) == 2


def test_parse_invalid_operator() -> None:
    with pytest.raises(FilterParseError):
        parse_sys_updated_on_filters("sys_updated_on.ne.2021-08-03+14:09:24")


def test_parse_invalid_timestamp() -> None:
    with pytest.raises(FilterParseError):
        parse_sys_updated_on_filters("sys_updated_on.gt.badtime")

