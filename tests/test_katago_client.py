"""KataGo 客户端单元测试：info 行解析（不依赖真实引擎）。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.katago_client import parse_info_lines  # noqa: E402


class TestParseInfoLines:
    def test_parse_real_format(self):
        line = ("info move D4 visits 3843 edgeVisits 3844 utility -0.259335 "
                "winrate 0.370788 scoreMean -0.733727 scoreStdev 13.1484 "
                "scoreLead -0.733727")
        cands = parse_info_lines([line])
        assert cands[0]["move"] == "D4"
        assert cands[0]["winrate"] == pytest.approx(0.370788)
        assert cands[0]["scoreLead"] == pytest.approx(-0.733727)
        assert cands[0]["visits"] == 3843
        assert cands[0]["pv"] == []  # 无 pv 字段

    def test_pv_parsed(self):
        line = ("info move D4 visits 100 winrate 0.5 scoreLead 0.0 "
                "scoreSelfplay -1.0 prior 0.05 lcb 0.1 weight 1 order 0 "
                "pv D4 Q16 D16 C17")
        cands = parse_info_lines([line])
        assert cands[0]["pv"] == ["D4", "Q16", "D16", "C17"]

    def test_multiple_moves_sorted_by_winrate(self):
        lines = [
            "info move A1 visits 10 winrate 0.2 scoreLead -3.0",
            "info move B2 visits 20 winrate 0.9 scoreLead 5.0",
            "info move C3 visits 30 winrate 0.5 scoreLead 1.0",
        ]
        cands = parse_info_lines(lines)
        assert [c["move"] for c in cands] == ["B2", "C3", "A1"]

    def test_lowercase_coords(self):
        line = "info move q16 visits 5 winrate 0.61 scoreLead 2.5"
        cands = parse_info_lines([line])
        assert cands[0]["move"] == "q16"
        assert cands[0]["winrate"] == pytest.approx(0.61)

    def test_dedupe_keeps_latest_visits(self):
        lines = [
            "info move D4 visits 10 winrate 0.3 scoreLead -1.0",
            "info move D4 visits 50 winrate 0.4 scoreLead 2.0",
            "info move E5 visits 20 winrate 0.35 scoreLead 0.0",
        ]
        cands = parse_info_lines(lines)
        d4 = next(c for c in cands if c["move"] == "D4")
        assert d4["visits"] == 50
        assert d4["winrate"] == pytest.approx(0.4)

    def test_negative_winrate_handled(self):
        """KataGo 早期 info 行可能出现 winrate 0 / 极小值，不应崩溃。"""
        lines = [
            "info move Q16 visits 0 edgeVisits 0 utility -1.17817 winrate 0 "
            "scoreMean -28.0372 scoreStdev 15.0289 scoreLead -28.0372",
        ]
        cands = parse_info_lines(lines)
        assert cands[0]["winrate"] == 0.0

    def test_empty_lines(self):
        assert parse_info_lines([]) == []
        assert parse_info_lines(["= KataGo", "", "info garbage"]) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
