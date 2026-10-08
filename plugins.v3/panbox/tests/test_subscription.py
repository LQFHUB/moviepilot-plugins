"""网盘订阅与同步引擎的纯逻辑单测（不联网、不依赖 MoviePilot 宿主）。

被测模块按文件路径加载，避免导入插件包 ``__init__``（它依赖宿主 ``app.sdk``）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    """按文件路径加载被测模块并注册到 sys.modules。"""
    spec = importlib.util.spec_from_file_location(name, _PLUGIN_DIR / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


subscription = _load("panbox_subscription_under_test", "core/subscription.py")


class _FakePlugin:
    """最小化的宿主插件桩：只提供 KV 读写。"""

    def __init__(self) -> None:
        self.kv = {}

    def get_data(self, key=None, plugin_id=None):
        """读取插件数据。"""
        return self.kv.get(key)

    def save_data(self, key, value, plugin_id=None):
        """保存插件数据。"""
        self.kv[key] = value


def _store() -> object:
    """构造一个绑定桩插件的订阅存储。"""
    return subscription.SubscriptionStore(_FakePlugin())


def test_订阅增删改查() -> None:
    """新增、按类型查询、更新、删除均可用。"""
    store = _store()
    movie = store.add({"title": "沙丘2", "media_type": "movie", "media_id": "693134", "year": "2024"})
    tv = store.add({"title": "末日地堡", "media_type": "tv", "media_id": "125988", "season": 3})
    assert movie.id and tv.id
    assert len(store.list_by_type("movie")) == 1
    assert len(store.list_by_type("tv")) == 1
    assert store.get(tv.id).season == 3

    updated = store.update(tv.id, {"enabled": False, "prefer_keywords": "4K"})
    assert updated.enabled is False and updated.prefer_keywords == "4K"

    assert store.delete(movie.id) is True
    assert store.delete(movie.id) is False
    assert len(store.all()) == 1


def test_按媒体去重() -> None:
    """同一媒体 ID + 类型视为同一订阅。"""
    store = _store()
    store.add({"title": "沙丘2", "media_type": "movie", "media_id": "693134"})
    assert store.find_by_media("693134", "movie") is not None
    assert store.find_by_media("693134", "tv") is None
    assert store.find_by_media("", "movie") is None


def test_记录同步结果会累计并截断() -> None:
    """转存记录会累计，且 seen 去重、长度受限。"""
    store = _store()
    sub = store.add({"title": "沙丘2", "media_type": "movie"})
    store.record_run(sub.id, 3, "首轮", transferred=[{"key": "a"}], seen=["a", "b", "b"])
    store.record_run(sub.id, 1, "二轮", transferred=[{"key": "c"}], seen=["c"])
    current = store.get(sub.id)
    assert [item["key"] for item in current.transferred] == ["a", "c"]
    assert current.seen == ["a", "b", "c"]
    assert current.last_candidates == 1 and current.last_message == "二轮"
    assert current.last_run_at > 0


def test_订阅序列化往返() -> None:
    """to_dict / from_dict 往返后关键字段一致。"""
    original = subscription.Subscription.from_dict(
        {"title": "沙丘2", "media_type": "TV", "poster": "https://x/p.jpg", "media_id": "693134"}
    )
    assert original.media_type == "tv"
    data = original.to_dict()
    assert data["poster_url"] == "https://x/p.jpg"
    restored = subscription.Subscription.from_dict(data)
    assert restored.id == original.id and restored.title == original.title
    assert restored.media_type == original.media_type
    assert restored.poster == original.poster


def test_类型兜底为电影() -> None:
    """非法或缺失类型时回落到 movie。"""
    assert subscription.Subscription.from_dict({"title": "x", "media_type": "anime"}).media_type == "movie"
    assert subscription.Subscription.from_dict({"title": "x"}).media_type == "movie"


def test_季号匹配与关键词拆分() -> None:
    """季号识别覆盖 S03 / 第3季 / Season 3；关键词按中英文逗号与空格拆分。"""
    matching = _load("panbox_matching_under_test", "core/matching.py")
    assert matching.match_season("末日地堡 S03 1080p", 3) is True
    assert matching.match_season("末日地堡 第三季", 3) is True
    assert matching.match_season("末日地堡 Season 3", 3) is True
    assert matching.match_season("末日地堡 S02", 3) is False
    assert matching.match_season("末日地堡 第三季", 0) is False
    assert matching.split_words("4K, 2160p，REMUX 高码") == ["4K", "2160p", "REMUX", "高码"]
    assert matching.split_words(["4K", " 1080p ", ""]) == ["4K", "1080p"]
    assert matching.score_preference("沙丘2 4K REMUX", ["4k", "remux", "1080p"]) == 2
    # 中文数字季号（实测 TG 资源里很常见）
    assert matching.match_season("末日地堡 第十二季", 12) is True
    assert matching.match_season("末日地堡 第二十季", 20) is True
    assert matching.match_season("末日地堡 第十季", 10) is True
    assert matching.parse_number("23") == 23
    assert matching.parse_number("三") == 3
    assert matching.parse_number("二十三") == 23
    assert matching.parse_number("十") == 10
    assert matching.parse_number("乱码") == 0
