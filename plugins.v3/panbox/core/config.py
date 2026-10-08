"""PanBox 配置定义。

Vue 联邦模式下 ``get_form()`` 不返回 Vuetify 组件树，只返回默认配置；
实际配置由宿主通过 ``PUT /api/v1/plugin/{plugin_id}`` 持久化。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .tg import DEFAULT_CHANNELS

__all__ = ["DEFAULT_CONFIG", "build_config"]

#: 插件默认配置。键名会原样出现在宿主配置与前端表单中。
DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    # 搜索
    "channels": DEFAULT_CHANNELS,
    "search_limit": 30,
    "search_timeout": 20,
    "search_filter": True,
    "search_base_url": "https://t.me/s",
    "search_proxy": "",
    # 115 网盘
    "p115_enabled": False,
    "p115_cookie": "",
    "p115_transfer_cid": "0",
    "p115_transfer_path": "",
    # 历史
    "history_limit": 500,
    "history_auto_record": True,
}


def build_config(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    """把宿主传入的配置与默认值合并。

    :param raw: 宿主保存的原始配置，可为 ``None``
    :return: 完整配置字典
    """
    config = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        config.update({key: value for key, value in raw.items() if key in DEFAULT_CONFIG})
    channels: List[Any] = config.get("channels") or []
    config["channels"] = [item for item in channels if isinstance(item, dict) and item.get("id")]
    for key in ("search_limit", "search_timeout", "history_limit"):
        try:
            config[key] = int(config.get(key) or DEFAULT_CONFIG[key])
        except (TypeError, ValueError):
            config[key] = DEFAULT_CONFIG[key]
    for key in ("enabled", "search_filter", "p115_enabled", "history_auto_record"):
        config[key] = bool(config.get(key))
    return config
