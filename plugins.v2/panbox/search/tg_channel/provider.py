"""TG 频道搜索能力声明。"""

from typing import Any, Iterable, Mapping

from ...core.search import (
    SearchCapability,
    SearchPolicy,
    SearchProvider,
)


def create_tg_channel_provider(
        service: Any,
        resource_types: Iterable[str],
        cache_context: Mapping[str, Any],
) -> SearchProvider:
    """创建 TG 频道搜索能力提供者。"""
    return SearchProvider(
        key="tg_channel",
        name="TG 频道",
        resource_types=frozenset(resource_types),
        services={
            SearchCapability.RESOURCE_SEARCH: service,
            SearchCapability.CACHE_MAINTENANCE: service,
        },
        policy=SearchPolicy(cache_context=cache_context),
    )
