"""Pure, dependency-free evaluation logic for the Price Alert Tool."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import csv
import json
import math
from pathlib import Path
from typing import Callable, Iterable


Warn = Callable[[str], None]


@dataclass(frozen=True)
class Price:
    day: date
    instrument: str
    close: Decimal


@dataclass(frozen=True)
class Rule:
    id: str
    instrument: str
    type: str
    direction: str
    level: Decimal | None = None
    level_text: str | None = None
    short: int | None = None
    long: int | None = None


@dataclass(frozen=True)
class Alert:
    day: date
    rule_id: str
    instrument: str
    kind: str
    detail: str

    def line(self) -> str:
        return f"{self.day.isoformat()} {self.rule_id} {self.instrument} {self.kind} {self.detail}"


class InputError(ValueError):
    """A whole input file is unusable and should produce exit code 2."""


def _clean(value: object) -> str:
    return str(value).strip()


def _decimal(value: object) -> Decimal:
    text = _clean(value)
    candidate = Decimal(text)
    if not candidate.is_finite():
        raise InvalidOperation
    return candidate


def load_prices(path: str | Path, warn: Warn) -> dict[str, list[Price]]:
    """Read valid rows, retaining the final row for duplicate date/instrument keys."""
    rows: dict[tuple[str, date], Price] = {}
    skipped = 0
    try:
        stream = open(path, "r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError(f"Could not read prices file: {exc}") from exc
    with stream:
        reader = csv.reader(stream)
        header: list[str] | None = None
        for line_number, raw in enumerate(reader, start=1):
            if not raw or not any(cell.strip() for cell in raw):
                continue
            if header is None:
                header = [cell.strip().lower() for cell in raw]
                missing = {"date", "instrument", "close"} - set(header)
                if missing:
                    raise InputError("Prices CSV is missing required column(s): " + ", ".join(sorted(missing)))
                continue
            padded = raw + [""] * max(0, len(header) - len(raw))
            values = dict(zip(header, padded))
            try:
                day = date.fromisoformat(_clean(values["date"]))
                instrument = _clean(values["instrument"]).upper()
                close = _decimal(values["close"])
                if not instrument or close <= 0:
                    raise ValueError
            except (ValueError, InvalidOperation, KeyError):
                skipped += 1
                warn(f"Warning: skipped malformed price row at line {line_number}.")
                continue
            key = (instrument, day)
            if key in rows:
                warn(f"Warning: duplicate price for {instrument} on {day.isoformat()} at line {line_number}; keeping last occurrence.")
            rows[key] = Price(day, instrument, close)
    if header is None:
        return {}
    grouped: dict[str, list[Price]] = defaultdict(list)
    for item in rows.values():
        grouped[item.instrument].append(item)
    for values in grouped.values():
        values.sort(key=lambda item: item.day)
    if skipped:
        warn(f"Warning: skipped {skipped} malformed price row(s).")
    return dict(grouped)


def _valid_rule(raw: object, ids: set[str], warn: Warn, index: int) -> Rule | None:
    if not isinstance(raw, dict):
        warn(f"Warning: rule {index} is not an object; skipped.")
        return None
    try:
        rule_id = _clean(raw["id"])
        instrument = _clean(raw["instrument"]).upper()
        kind = _clean(raw["type"])
        direction = _clean(raw["direction"]).lower()
        if not rule_id or not instrument or rule_id in ids or direction not in {"above", "below"}:
            raise ValueError
        if kind == "level":
            level_text = _clean(raw["level"])
            level = _decimal(level_text)
            if level <= 0:
                raise ValueError
            result = Rule(rule_id, instrument, kind, direction, level=level, level_text=level_text)
        elif kind == "ma_cross":
            short, long = raw["short"], raw["long"]
            if isinstance(short, bool) or isinstance(long, bool):
                raise ValueError
            if not isinstance(short, int) or not isinstance(long, int) or short <= 0 or long <= 0 or short >= long:
                raise ValueError
            result = Rule(rule_id, instrument, kind, direction, short=short, long=long)
        else:
            raise ValueError
    except (KeyError, ValueError, InvalidOperation):
        warn(f"Warning: invalid rule {index}; skipped.")
        return None
    ids.add(result.id)
    return result


def load_rules(path: str | Path, warn: Warn) -> list[Rule]:
    try:
        with open(path, "r", encoding="utf-8-sig") as stream:
            raw_rules = json.load(stream)
    except OSError as exc:
        raise InputError(f"Could not read rules file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"Rules JSON is malformed: {exc.msg}") from exc
    if not isinstance(raw_rules, list):
        raise InputError("Rules JSON must be a list.")
    ids: set[str] = set()
    return [rule for index, raw in enumerate(raw_rules, start=1) if (rule := _valid_rule(raw, ids, warn, index))]


def _smas(values: list[Decimal], window: int) -> list[Decimal | None]:
    output: list[Decimal | None] = [None] * len(values)
    total = Decimal(0)
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        if index >= window - 1:
            output[index] = total / Decimal(window)
    return output


def evaluate(prices: dict[str, list[Price]], rules: Iterable[Rule], warn: Warn = lambda _: None) -> list[Alert]:
    alerts: list[Alert] = []
    sma_cache: dict[tuple[str, int], list[Decimal | None]] = {}
    for rule in rules:
        series = prices.get(rule.instrument)
        if not series:
            warn(f"Warning: rule {rule.id!r} has no price data for {rule.instrument}.")
            continue
        closes = [item.close for item in series]
        if rule.type == "level":
            assert rule.level is not None and rule.level_text is not None
            for index in range(1, len(series)):
                previous, current = closes[index - 1], closes[index]
                crossed = (rule.direction == "above" and previous <= rule.level < current) or (
                    rule.direction == "below" and previous >= rule.level > current
                )
                if crossed:
                    alerts.append(Alert(series[index].day, rule.id, rule.instrument, "level", f"{rule.direction} {rule.level_text}"))
        else:
            assert rule.short is not None and rule.long is not None
            short_key, long_key = (rule.instrument, rule.short), (rule.instrument, rule.long)
            sma_cache.setdefault(short_key, _smas(closes, rule.short))
            sma_cache.setdefault(long_key, _smas(closes, rule.long))
            short_sma, long_sma = sma_cache[short_key], sma_cache[long_key]
            for index in range(1, len(series)):
                previous_short, previous_long = short_sma[index - 1], long_sma[index - 1]
                current_short, current_long = short_sma[index], long_sma[index]
                if None in (previous_short, previous_long, current_short, current_long):
                    continue
                crossed = (rule.direction == "above" and previous_short <= previous_long and current_short > current_long) or (
                    rule.direction == "below" and previous_short >= previous_long and current_short < current_long
                )
                if crossed:
                    alerts.append(Alert(series[index].day, rule.id, rule.instrument, "ma_cross", f"{rule.short}/{rule.long} {rule.direction}"))
    return sorted(alerts, key=lambda item: (item.day, item.rule_id))


def run(prices_path: str | Path, rules_path: str | Path, warn: Warn) -> list[Alert]:
    return evaluate(load_prices(prices_path, warn), load_rules(rules_path, warn), warn)
