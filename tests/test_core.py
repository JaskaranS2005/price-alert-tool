from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from alerts_core import InputError, Price, Rule, evaluate, load_prices, load_rules


def series(values: list[str]) -> dict[str, list[Price]]:
    return {"INFY": [Price(date(2026, 1, index + 1), "INFY", Decimal(value)) for index, value in enumerate(values)]}


def lines(values: list[str], rule: Rule) -> list[str]:
    return [item.line() for item in evaluate(series(values), [rule])]


class AlertEvaluationTests(unittest.TestCase):
    def test_brief_example_crosses_below_level(self) -> None:
        rule = Rule("r1", "INFY", "level", "below", level=Decimal("1500"), level_text="1500")
        self.assertEqual(lines(["1520.50", "1534.10", "1498.00"], rule), ["2026-01-03 r1 INFY level below 1500"])

    def test_level_requires_a_genuine_crossing_and_can_refire(self) -> None:
        rule = Rule("cross", "INFY", "level", "above", level=Decimal("10"), level_text="10")
        self.assertEqual(lines(["10", "10", "11", "10", "12"], rule), ["2026-01-03 cross INFY level above 10", "2026-01-05 cross INFY level above 10"])

    def test_ma_cross_above_hand_computed(self) -> None:
        # At day 3 both averages equal 2; at day 4 short=(1+7)/2=4 and long=(2+1+7)/3=10/3.
        rule = Rule("ma", "INFY", "ma_cross", "above", short=2, long=3)
        self.assertEqual(lines(["2", "3", "1", "7"], rule), ["2026-01-04 ma INFY ma_cross 2/3 above"])

    def test_ma_cross_below_and_equal_smas_do_not_fire(self) -> None:
        below = Rule("ma", "INFY", "ma_cross", "below", short=2, long=3)
        above = Rule("ma", "INFY", "ma_cross", "above", short=2, long=3)
        self.assertEqual(lines(["7", "11", "3", "1"], below), ["2026-01-04 ma INFY ma_cross 2/3 below"])
        self.assertEqual(lines(["4", "4", "4", "4"], above), [])

    def test_short_series_and_first_row_never_alert(self) -> None:
        level = Rule("first", "INFY", "level", "above", level=Decimal("1"), level_text="1")
        ma = Rule("short", "INFY", "ma_cross", "above", short=2, long=3)
        self.assertEqual(lines(["2"], level), [])
        self.assertEqual(lines(["1", "2"], ma), [])


class InputHandlingTests(unittest.TestCase):
    def test_rows_are_normalized_sorted_and_last_duplicate_wins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "prices.csv"
            source.write_text("\ufeff DATE , Instrument , Close , ignored\r\n2026-01-02, infy, 9,x\r\n2026-01-01,INFY,10,x\r\n2026-01-02,INFY,11,x\r\n", encoding="utf-8")
            warnings: list[str] = []
            prices = load_prices(source, warnings.append)
        self.assertEqual([item.close for item in prices["INFY"]], [Decimal("10"), Decimal("11")])
        self.assertTrue(any("duplicate" in message for message in warnings))

    def test_bad_rows_invalid_rules_and_unknown_instrument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            prices, rules = path / "prices.csv", path / "rules.json"
            prices.write_text("date,instrument,close\n2026-01-01,INFY,10\nbad,INFY,12\n2026-01-02,INFY,NaN\n", encoding="utf-8")
            rules.write_text(json.dumps([{"id":"ok","instrument":"INFY","type":"level","direction":"above","level":10}, {"id":"bad","instrument":"INFY","type":"ma_cross","short":3,"long":2,"direction":"above"}, {"id":"none","instrument":"TCS","type":"level","direction":"above","level":1}]), encoding="utf-8")
            warnings: list[str] = []
            loaded_prices, loaded_rules = load_prices(prices, warnings.append), load_rules(rules, warnings.append)
            self.assertEqual([rule.id for rule in loaded_rules], ["ok", "none"])
            self.assertEqual(evaluate(loaded_prices, loaded_rules, warnings.append), [])
        self.assertTrue(any("skipped 2" in message for message in warnings))
        self.assertTrue(any("no price data" in message for message in warnings))

    def test_whole_file_errors_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            bad_header, bad_rules = path / "bad.csv", path / "bad.json"
            bad_header.write_text("date,close\n2026-01-01,1\n", encoding="utf-8")
            bad_rules.write_text("{}", encoding="utf-8")
            with self.assertRaises(InputError): load_prices(bad_header, lambda _: None)
            with self.assertRaises(InputError): load_rules(bad_rules, lambda _: None)
