"""Extract a datetime from a filename using a human-friendly pattern.

The pattern uses tokens like ``yyyy-mm-dd_HH-mm-ss`` or ``yyyymmddHHmmss``.
Everything that is not a token is matched literally, and the pattern is
searched for anywhere inside the filename, so ``IMG_20230115_report.jpg``
matches ``yyyymmdd``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# Token -> (field, number of digits). ``mm``/``MM`` are ambiguous (month or
# minute) and resolved by position, see _field_for_ambiguous_token().
_TOKENS: list[tuple[str, str, int]] = [
    ("yyyy", "year", 4),
    ("yy", "year2", 2),
    ("mm", "?", 2),
    ("MM", "?", 2),
    ("dd", "day", 2),
    ("DD", "day", 2),
    ("HH", "hour", 2),
    ("hh", "hour", 2),
    ("nn", "minute", 2),  # explicit minute alias
    ("mi", "minute", 2),  # explicit minute alias
    ("ss", "second", 2),
    ("SS", "second", 2),
]

_DEFAULTS = {"month": 1, "day": 1, "hour": 0, "minute": 0, "second": 0}


class PatternError(ValueError):
    """The user supplied a pattern that cannot be used."""


@dataclass(frozen=True)
class CompiledPattern:
    regex: re.Pattern[str]
    fields: tuple[str, ...]

    def parse(self, filename: str) -> datetime:
        """Return the datetime encoded in *filename*.

        Raises ValueError when the pattern does not match or the matched
        numbers do not form a real date.
        """
        match = self.regex.search(filename)
        if match is None:
            raise ValueError("filename does not match the pattern")

        values = {name: int(match.group(name)) for name in self.fields}
        if "year2" in values:
            two = values.pop("year2")
            values["year"] = 2000 + two if two < 70 else 1900 + two

        parts = dict(_DEFAULTS)
        parts.update(values)
        try:
            return datetime(
                parts["year"],
                parts["month"],
                parts["day"],
                parts["hour"],
                parts["minute"],
                parts["second"],
            )
        except ValueError as exc:  # e.g. month 13, day 31 in February
            raise ValueError(f"invalid date in filename ({exc})") from exc


def _field_for_ambiguous_token(assigned: set[str]) -> str:
    """Decide whether an ``mm`` token means month or minute.

    Rule of thumb, matching how people write these patterns: the first
    ``mm`` is the month, unless an hour has already been seen, in which
    case it is the minute.
    """
    hour_seen = "hour" in assigned
    if hour_seen and "minute" not in assigned:
        return "minute"
    if "month" not in assigned:
        return "month"
    if "minute" not in assigned:
        return "minute"
    raise PatternError("month and minute are both already defined in the pattern")


def compile_pattern(pattern: str) -> CompiledPattern:
    """Turn a user pattern into a regex that captures the date fields."""
    pattern = pattern.strip()
    if not pattern:
        raise PatternError("the timestamp format is empty")

    assigned: set[str] = set()
    fields: list[str] = []
    regex_parts: list[str] = []
    i = 0
    while i < len(pattern):
        for token, field, width in _TOKENS:
            if pattern.startswith(token, i):
                if field == "?":
                    field = _field_for_ambiguous_token(assigned)
                elif field in assigned or (field == "year2" and "year" in assigned):
                    raise PatternError(f"'{token}' appears more than once in the pattern")
                assigned.add("year" if field == "year2" else field)
                fields.append(field)
                regex_parts.append(rf"(?P<{field}>\d{{{width}}})")
                i += len(token)
                break
        else:
            regex_parts.append(re.escape(pattern[i]))
            i += 1

    if "year" not in assigned:
        raise PatternError("the pattern must contain a year (yyyy or yy)")
    if "month" not in assigned and "day" in assigned:
        raise PatternError("the pattern has a day but no month")

    # Do not let a number token start or end in the middle of a longer run of
    # digits: that avoids matching 8 digits of a 10 digit sequence.
    body = "".join(regex_parts)
    return CompiledPattern(re.compile(rf"(?<!\d){body}(?!\d)"), tuple(fields))
