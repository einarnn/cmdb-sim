from __future__ import annotations

import re
from datetime import datetime
from typing import Callable
from urllib.parse import unquote_plus

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
FILTER_PATTERN = re.compile(r"^sys_updated_on\.(gt|gte|lt|lte|eq)\.(.+)$")

Predicate = Callable[[datetime], bool]


class FilterParseError(ValueError):
    """Raised when filter syntax is invalid."""


def parse_timestamp(value: str) -> datetime:
    try:
        return datetime.strptime(value, TS_FORMAT)
    except ValueError as exc:
        raise FilterParseError(
            f"Invalid timestamp '{value}'. Expected format: {TS_FORMAT}"
        ) from exc


def parse_sys_updated_on_filters(raw_query_string: str) -> list[Predicate]:
    if not raw_query_string:
        return []

    predicates: list[Predicate] = []
    saw_sys_updated_on_token = False

    for part in raw_query_string.split("&"):
        if not part:
            continue
        decoded = unquote_plus(part)

        candidates = [decoded]
        if "=" in decoded:
            key, value = decoded.split("=", 1)
            candidates = [key]
            if value:
                candidates.append(value)

        parsed = False
        for candidate in candidates:
            if "sys_updated_on" in candidate:
                saw_sys_updated_on_token = True
            match = FILTER_PATTERN.match(candidate)
            if not match:
                continue

            op, rhs = match.group(1), match.group(2)
            rhs_dt = parse_timestamp(rhs)
            predicates.append(_operator_predicate(op, rhs_dt))
            parsed = True
            break

        if "sys_updated_on" in decoded and not parsed:
            raise FilterParseError(
                "Invalid sys_updated_on filter. "
                "Expected syntax: sys_updated_on.<gt|gte|lt|lte|eq>.<YYYY-MM-DD HH:MM:SS>"
            )

    if saw_sys_updated_on_token and not predicates:
        raise FilterParseError(
            "sys_updated_on filter provided but no valid operator was found."
        )

    return predicates


def _operator_predicate(op: str, rhs: datetime) -> Predicate:
    if op == "gt":
        return lambda lhs: lhs > rhs
    if op == "gte":
        return lambda lhs: lhs >= rhs
    if op == "lt":
        return lambda lhs: lhs < rhs
    if op == "lte":
        return lambda lhs: lhs <= rhs
    if op == "eq":
        return lambda lhs: lhs == rhs
    raise FilterParseError(f"Unsupported operator: {op}")

