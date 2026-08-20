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


class TestMultiCandidateLine:
    """KataGo 把一次刷新的所有候选拼在同一行，必须逐块拆开解析。"""

    LINE = (
        "info move D4 visits 148 utility 0.316 winrate 0.654944 scoreMean 0.865 "
        "scoreStdev 12.7 scoreLead 0.865254 order 0 pv D4 C17 D17 C16 "
        "info move D3 visits 32 utility 0.273 winrate 0.636003 scoreMean 0.681 "
        "scoreStdev 12.8 scoreLead 0.681544 order 1 pv D3 C17 D17 "
        "info move C4 visits 19 utility 0.261 winrate 0.632100 scoreMean 0.554 "
        "scoreStdev 12.9 scoreLead 0.554000 order 2 pv C4 C17 D17 C16 D15"
    )

    def test_all_candidates_parsed(self):
        cands = parse_info_lines([self.LINE])
        assert [c["move"] for c in cands] == ["D4", "D3", "C4"]

    def test_pv_not_polluted_by_next_block(self):
        """回归：贪婪 pv 会把后续 'info move ...' 一起吞进变化图。"""
        cands = parse_info_lines([self.LINE])
        d4 = next(c for c in cands if c["move"] == "D4")
        assert d4["pv"] == ["D4", "C17", "D17", "C16"]
        assert all("info" not in c["pv"] for c in cands)

    def test_visits_not_truncated(self):
        """回归：只解析首块时，后续候选的 visits 会停留在偏小的旧快照。"""
        cands = parse_info_lines([self.LINE])
        assert {c["move"]: c["visits"] for c in cands} == {"D4": 148, "D3": 32, "C4": 19}

    def test_last_block_without_pv(self):
        line = ("info move D4 visits 5 winrate 0.5 scoreLead 0.0 pv D4 Q16 "
                "info move E5 visits 3 winrate 0.4 scoreLead -1.0")
        cands = parse_info_lines([line])
        assert next(c for c in cands if c["move"] == "E5")["pv"] == []


class TestInvalidWinrate:
    """胜率越界即无效数据：让它进候选就等于让 AI 推荐一个垃圾着法。"""

    def test_drops_out_of_range_winrate(self):
        lines = ["info move D4 visits 100 winrate 9.97 scoreLead 0.5",
                 "info move Q16 visits 50 winrate 0.62 scoreLead 1.0"]
        cands = parse_info_lines(lines)
        assert [c["move"] for c in cands] == ["Q16"]

    def test_keeps_boundary_values(self):
        lines = ["info move A1 visits 1 winrate 0 scoreLead -50.0",
                 "info move T19 visits 1 winrate 1 scoreLead 50.0"]
        assert len(parse_info_lines(lines)) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
