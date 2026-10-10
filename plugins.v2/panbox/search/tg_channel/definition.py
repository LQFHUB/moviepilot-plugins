"""TG 频道搜索渠道自描述规范与表单声明。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import TelegramChannelClient
from .provider import create_tg_channel_provider
from .service import TelegramChannelSearchService
from ...core.config import DEFAULT_TG_CHANNEL_ITEMS
from ...core.definitions import FieldSpec, GroupSpec, SearchSourceDefinition
from ..types import SUPPORTED_RESOURCE_TYPES


class TelegramChannelSourceDefinition(SearchSourceDefinition):
    """Telegram 公开频道搜索渠道规范。"""

    id = "tg_channel"
    name = "TG 频道"
    icon = "mdi-telegram"
    color = "light-blue"
    order = 55

    @classmethod
    def _channel_items(cls, config: Dict[str, Any]) -> Any:
        """读取并归一化频道配置为 ``{id, name, icon}`` 对象列表。"""
        raw = cls.config_value(
            config, "tg_channels", [dict(item) for item in DEFAULT_TG_CHANNEL_ITEMS]
        )
        return TelegramChannelClient.normalize_channel_items(raw or [])

    @classmethod
    def create_client(cls, config: Dict[str, Any], context: Optional[Any] = None) -> Any:
        """按配置构建 TG 频道抓取客户端；未启用或无有效频道时返回 None。"""
        if not bool(cls.config_value(config, "tg_channel_search_enabled", True)):
            return None
        if not cls._channel_items(config):
            return None
        return TelegramChannelClient(
            proxy=(context or {}).get("proxy"),
            request_timeout=int(
                cls.config_value(config, "tg_channel_request_timeout", 15) or 15
            ),
            request_interval=float(
                cls.config_value(config, "tg_channel_request_interval", 1.0) or 1.0
            ),
        )

    @classmethod
    def resolve_source_info(
            cls,
            config: Any,
            context: Optional[Dict[str, Any]] = None,
            value: Any = "",
    ) -> Dict[str, Any]:
        """抓取指定 TG 频道的名称与头像，供配置页自动填充。"""
        channel = TelegramChannelClient.normalize_channel(value)
        if not channel:
            raise ValueError("频道用户名不合法（只允许字母、数字与下划线，长度 3~64）")
        client = TelegramChannelClient(
            proxy=(context or {}).get("proxy"),
            request_timeout=int(
                cls.config_value(config, "tg_channel_request_timeout", 15) or 15
            ),
            request_interval=0,
        )
        info = client.fetch_channel_info(channel, force=True)
        return {
            "id": channel,
            "name": str(info.get("name") or channel),
            "icon": str(info.get("icon") or ""),
        }

    @classmethod
    def get_config_groups(
            cls, context: Optional[Dict[str, Any]] = None
    ) -> List[GroupSpec]:
        """返回 TG 频道搜索的表单分组与字段定义。"""
        return [
            GroupSpec(
                tab="tg_channel",
                title="TG 频道搜索",
                icon="mdi-telegram",
                hint="抓取 https://t.me/s/<频道> 公开预览页，仅支持公开频道。",
                fields=[
                    FieldSpec(
                        key="tg_channel_search_enabled",
                        label="启用 TG 频道搜索",
                        type="switch",
                        default=True,
                        cols=4,
                    ),
                    FieldSpec(
                        key="tg_channels",
                        label="TG 频道列表",
                        type="channel-list",
                        default=[dict(item) for item in DEFAULT_TG_CHANNEL_ITEMS],
                        placeholder="QukanMovie",
                        hint="每行填频道的用户名（不含 @ 与 t.me/s/ 前缀）与频道名称；"
                             "名称留空时会自动从频道公开页获取，频道图标一律自动抓取（无需填写）。"
                             "站内搜索为模糊匹配，结果会按关键词二次过滤。",
                        cols=12,
                        # 前端用该标识请求「自动获取名称与图标」接口。
                        source=cls.id,
                    ),
                    FieldSpec(
                        key="test_tg_channel",
                        label="测试搜索",
                        type="test-source",
                        source="tg_channel",
                        cols=12,
                    ),
                ],
            ),
            GroupSpec(
                tab="tg_channel",
                title="抓取与限速",
                icon="mdi-speedometer",
                hint="频道较多时建议保留请求间隔，避免触发 Telegram 限流。",
                fields=[
                    FieldSpec(
                        key="tg_channel_result_limit",
                        label="候选上限",
                        type="number",
                        default=20,
                        min=1,
                        max=80,
                        cols=4,
                    ),
                    FieldSpec(
                        key="tg_channel_timeout",
                        label="搜索超时",
                        hint="全部频道共享的总时长",
                        type="number",
                        default=60,
                        min=5,
                        max=120,
                        suffix="秒",
                        cols=4,
                    ),
                    FieldSpec(
                        key="tg_channel_request_timeout",
                        label="单次请求超时",
                        type="number",
                        default=15,
                        min=5,
                        max=60,
                        suffix="秒",
                        cols=4,
                    ),
                    FieldSpec(
                        key="tg_channel_request_interval",
                        label="频道间隔",
                        type="number",
                        default=1.0,
                        min=0.2,
                        max=10,
                        step=0.1,
                        suffix="秒",
                        cols=4,
                    ),
                ],
            ),
        ]

    @classmethod
    def create_provider(
            cls, service: Any, client: Any, config: Dict[str, Any], context: Optional[Any] = None
    ) -> Any:
        """构建 TG 频道搜索 Provider；客户端或频道列表缺失时返回 None。"""
        ctx = context or {}
        if not client:
            return None
        channels = cls._channel_items(config)
        if not channels:
            return None
        resource_types = [
            value for value in (ctx.get("resource_types") or ())
            if value in SUPPORTED_RESOURCE_TYPES
        ] or list(SUPPORTED_RESOURCE_TYPES)
        result_limit = int(cls.config_value(config, "tg_channel_result_limit", 20) or 20)
        timeout = float(cls.config_value(config, "tg_channel_timeout", 60) or 60)
        search_service = service or TelegramChannelSearchService(
            client=client,
            channels=channels,
            result_limit=result_limit,
            timeout=timeout,
        )
        return create_tg_channel_provider(
            search_service,
            resource_types,
            {
                "channels": channels,
                "result_limit": result_limit,
                "timeout": timeout,
            },
        )
