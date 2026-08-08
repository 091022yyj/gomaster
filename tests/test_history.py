"""对局记录/战绩/SGF 单元测试。"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gomaster.history as H  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_data(monkeypatch, tmp_path):
    """把数据目录重定向到临时目录。"""
    monkeypatch.setattr(H, "data_dir", lambda: str(tmp_path))
    yield


class TestHistory:
    def test_save_and_list(self):
        moves = [(1, 3, 3), (-1, 15, 15)]
        rec = H.save_game(moves, source="test")
        games = H.list_games()
        assert len(games) == 1
        assert games[0]["moves"] == [[1, 3, 3], [-1, 15, 15]]

    def test_keep_last_30(self):
        for i in range(35):
            H.save_game([(1, 3, 3)], source="t")
        assert len(H.list_games()) == 30

    def test_stats(self):
        H.save_game([], result="B")
        H.save_game([], result="W")
        H.save_game([], result="B")
        s = H.stats()
        assert s["total"] == 3
        assert s["wins"] == 3  # B/W 都算我方胜（按胜负记录）

    def test_sgf_export(self):
        moves = [(1, 3, 3), (-1, 15, 15), (1, 0, 0)]
        sgf = H.moves_to_sgf(moves, 19, 7.5)
        assert "(;GM[1]FF[4]SZ[19]KM[7.5]" in sgf
        assert "B[dd]" in sgf
        assert "W[pp]" in sgf
        assert "B[aa]" in sgf
        # 导出文件
        p = H.export_sgf(moves, os.path.join(tempfile.gettempdir(), "t.sgf"))
        assert p and os.path.exists(p)
        os.remove(p)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
