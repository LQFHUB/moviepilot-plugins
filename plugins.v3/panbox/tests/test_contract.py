"""PanBox 插件契约测试（不联网、不依赖 MoviePilot 宿主）。

用桩模拟宿主 ``_PluginBase`` 的抽象方法与插件 KV，验证插件对宿主契约的遵守情况：
抽象方法是否齐全、``get_api`` 路由键名能否被 ``add_api_route`` 接受、
侧栏项字段是否满足 ``projection.py`` 的校验规则、以及各 API 的失败路径。

宿主规则来源（MoviePilot V3.1.1 源码）：
- ``app/runtime/extensions/plugin/projection.py``：侧栏字段与取值范围、API 路径前缀
- ``app/adapters/web/plugin/routes.py``：``add_api_route(**api)`` 直接透传，键名必须是合法参数
- ``app/sdk/plugin/base.py``：抽象方法集合
"""

from __future__ import annotations

import sys
import types
from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parents[1]
#: 插件包的上层目录（plugins.v3），把它加入 sys.path 后才能按顶层包导入 panbox
_PLUGINS_ROOT = Path(__file__).resolve().parents[2]


class _StubPluginBase(metaclass=ABCMeta):
    """按 MoviePilot V3.1.1 的真实抽象方法集合定义的宿主基类桩。"""

    plugin_name = ""
    plugin_desc = ""
    plugin_order = 9999

    def __init__(self) -> None:
        """初始化内存 KV，替代宿主持久化。"""
        self._kv: Dict[str, Any] = {}

    @abstractmethod
    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        """生效配置。"""

    @abstractmethod
    def get_state(self) -> bool:
        """插件启用状态。"""

    @abstractmethod
    def get_api(self) -> List[Dict[str, Any]]:
        """插件 API 列表。"""

    @abstractmethod
    def get_form(self) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
        """插件表单。"""

    @abstractmethod
    def get_page(self) -> Optional[List[Dict[str, Any]]]:
        """插件详情页。"""

    @abstractmethod
    def stop_service(self) -> None:
        """停止服务。"""

    def get_data(self, key: Optional[str] = None, plugin_id: Optional[str] = None) -> Any:
        """读取插件数据。"""
        return self._kv.get(key)

    def save_data(self, key: str, value: Any, plugin_id: Optional[str] = None) -> None:
        """保存插件数据。"""
        self._kv[key] = value

    def del_data(self, key: str, plugin_id: Optional[str] = None) -> None:
        """删除插件数据。"""
        self._kv.pop(key, None)


def _install_host_stubs() -> None:
    """在导入插件包之前注入 ``app.sdk`` 桩。"""
    app_module = types.ModuleType("app")
    app_module.__path__ = []
    sdk_module = types.ModuleType("app.sdk")
    sdk_module.__path__ = []
    plugin_module = types.ModuleType("app.sdk.plugin")
    plugin_module._PluginBase = _StubPluginBase
    network_module = types.ModuleType("app.sdk.network")
    network_module.RequestUtils = object
    network_module.AsyncRequestUtils = object
    sys.modules.setdefault("app", app_module)
    sys.modules.setdefault("app.sdk", sdk_module)
    sys.modules["app.sdk.plugin"] = plugin_module
    sys.modules["app.sdk.network"] = network_module


_install_host_stubs()

if str(_PLUGINS_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGINS_ROOT))

from panbox import PanBox  # noqa: E402

#: ``add_api_route`` 能接受的键（超出即为 TypeError）
_ALLOWED_ROUTE_KEYS = {
    "path",
    "endpoint",
    "methods",
    "auth",
    "summary",
    "description",
    "dependencies",
    "response_model",
    "allow_anonymous",
}

_SAMPLE_ITEM: Dict[str, Any] = {
    "channel_id": "Quark_Movies",
    "channel_name": "夸克云盘影视资源频道",
    "message_id": "71460",
    "title": "流浪地球2",
    "content": "4K HDR",
    "pub_date": "2026-08-14T02:57:28+00:00",
    "cloud_links": [
        {"cloud_type": "quark", "url": "https://pan.quark.cn/s/a158b5be345f", "receive_code": "k9t2"}
    ],
}


@pytest.fixture()
def plugin() -> PanBox:
    """返回一个已启用、已配置频道的插件实例。"""
    instance = PanBox()
    instance.init_plugin(
        {
            "enabled": True,
            "channels": [{"id": "Quark_Movies", "name": "夸克云盘影视资源频道"}],
        }
    )
    return instance


def test_抽象方法齐全且可实例化() -> None:
    """缺少任一抽象方法时实例化会 TypeError。"""
    instance = PanBox()
    assert isinstance(instance, _StubPluginBase)


def test_渲染模式为_vue_联邦(plugin: PanBox) -> None:
    """Vue 模式需声明构建产物目录，且表单/详情页不再返回 Vuetify 组件树。"""
    assert plugin.get_render_mode() == ("vue", "dist/assets")
    form, defaults = plugin.get_form()
    assert form is None
    assert isinstance(defaults, dict) and defaults["enabled"] is True
    assert plugin.get_page() is None


def test_侧栏项满足宿主校验规则(plugin: PanBox) -> None:
    """四个入口分别落在探索/订阅/系统分组；nav_key 与 section 必须合法。"""
    nav = plugin.get_sidebar_nav()
    assert [item["nav_key"] for item in nav] == ["resource", "movie", "tv", "main"]
    sections = {item["nav_key"]: item["section"] for item in nav}
    assert sections["resource"] == "discovery"
    assert sections["movie"] == "subscribe"
    assert sections["tv"] == "subscribe"
    assert sections["main"] == "system"
    for item in nav:
        assert item["section"] in {"start", "discovery", "subscribe", "organize", "system"}
        assert item["permission"] in {"subscribe", "discovery", "search", "manage", "admin"}
        assert not any(character in item["nav_key"] for character in "/?# ")
        assert item["title"]


def test_未启用时不下发侧栏入口() -> None:
    """侧栏入口仅对启用的插件下发。"""
    instance = PanBox()
    instance.init_plugin({"enabled": False})
    assert instance.get_sidebar_nav() == []


def test_api_路由键名与路径合法(plugin: PanBox) -> None:
    """路由字典会被原样透传给 FastAPI 的 add_api_route，键名必须合法。"""
    apis = plugin.get_api()
    assert apis
    for api in apis:
        assert set(api) <= _ALLOWED_ROUTE_KEYS, f"含不被 add_api_route 接受的键：{set(api) - _ALLOWED_ROUTE_KEYS}"
        assert api["path"].startswith("/")
        assert callable(api["endpoint"])
        assert api["methods"]
        assert api["auth"] == "bear"
    paths = [api["path"] for api in apis]
    assert len(set(paths)) == len(paths), "存在重复路由路径"


def test_收藏增删与去重(plugin: PanBox) -> None:
    """同一消息重复收藏应被拒绝，删除按记录 ID 生效。"""
    assert plugin.api_favorite_add({"item": _SAMPLE_ITEM, "note": "想看"})["success"] is True
    duplicate = plugin.api_favorite_add({"item": _SAMPLE_ITEM})
    assert duplicate["success"] is False
    favorites = plugin.api_favorites()["data"]
    assert len(favorites) == 1 and favorites[0]["note"] == "想看"
    assert plugin.api_favorite_delete({"id": favorites[0]["id"]})["success"] is True
    assert plugin.api_favorites()["data"] == []


def test_历史分页与过滤(plugin: PanBox) -> None:
    """历史支持分页、来源过滤、关键词过滤与清空。"""
    plugin._store.add_history(_SAMPLE_ITEM, source="search")
    plugin._store.add_history(_SAMPLE_ITEM, source="transfer")
    assert plugin.api_history()["data"]["total"] == 2
    assert plugin.api_history(source="transfer")["data"]["total"] == 1
    assert plugin.api_history(keyword="流浪")["data"]["total"] == 2
    assert plugin.api_history(keyword="不存在")["data"]["total"] == 0
    page = plugin.api_history(page=1, page_size=1)["data"]
    assert len(page["items"]) == 1 and page["total"] == 2
    record_id = page["items"][0]["id"]
    assert plugin.api_history_delete({"id": record_id})["success"] is True
    assert plugin.api_history()["data"]["total"] == 1
    assert "已清空" in plugin.api_history_clear()["message"]
    assert plugin.api_history()["data"]["total"] == 0


def test_失败路径返回可读结果(plugin: PanBox) -> None:
    """未启用、未配置 Cookie、缺参数时返回 success=False 而不是抛异常。"""
    assert plugin.api_transfer({})["success"] is False
    assert plugin.api_drive_folders()["success"] is False
    assert plugin.api_favorite_add({})["success"] is False
    assert plugin.api_history_delete({})["success"] is False
    assert plugin.api_favorite_delete({})["success"] is False

    disabled = PanBox()
    disabled.init_plugin({"enabled": False})
    result = disabled.api_search(keyword="测试")
    assert result["success"] is False and result["message"]

    unconfigured = PanBox()
    unconfigured.init_plugin({"enabled": True, "p115_enabled": True})
    result = unconfigured.api_transfer({"url": "https://115cdn.com/s/abc"})
    assert result["success"] is False and "Cookie" in result["message"]
