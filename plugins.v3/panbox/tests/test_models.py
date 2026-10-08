"""PanBox 纯逻辑单测（不联网、不依赖 MoviePilot 宿主）。

被测模块按文件路径加载，避免导入插件包 ``__init__``（它依赖宿主 ``app.sdk``）。

在插件目录下运行：``python -m pytest tests -q``
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODELS_PATH = Path(__file__).resolve().parents[1] / "core" / "models.py"
_spec = importlib.util.spec_from_file_location("panbox_models_under_test", _MODELS_PATH)
assert _spec and _spec.loader
models = importlib.util.module_from_spec(_spec)
# dataclasses 需要能从 sys.modules 找到模块自身，故先注册再执行
sys.modules[_spec.name] = models
_spec.loader.exec_module(models)

CloudLink = models.CloudLink
ResourceItem = models.ResourceItem
classify_cloud_links = models.classify_cloud_links
classify_cloud_type = models.classify_cloud_type
extract_receive_code = models.extract_receive_code
parse_share_url = models.parse_share_url

SAMPLE_TEXT = (
    "名称：流浪地球2 (2023) 4K HDR\n"
    "夸克：https://pan.quark.cn/s/a158b5be345f 提取码：k9t2\n"
    "115：https://115cdn.com/s/swsvxg73fwl?password=i2e8\n"
    "阿里：https://www.alipan.com/s/abc123xyz\n"
    "天翼：https://cloud.189.cn/t/AbCdEf\n"
    "123：https://www.123pan.com/s/abcd-efgh\n"
    "移动：https://caiyun.139.com/m/i?2abcd\n"
)


def test_classify_cloud_links_识别全部网盘类型() -> None:
    """应识别出文本中出现的全部六类网盘链接。"""
    links = classify_cloud_links(SAMPLE_TEXT)
    assert {link.cloud_type for link in links} == {"quark", "p115", "aliyun", "tianyi", "p123", "yun139"}


def test_classify_cloud_links_去重() -> None:
    """相同链接重复出现时只保留一条。"""
    links = classify_cloud_links("https://pan.quark.cn/s/abc https://pan.quark.cn/s/abc")
    assert len(links) == 1


def test_classify_cloud_links_空文本() -> None:
    """空文本不产生结果。"""
    assert classify_cloud_links("") == []


def test_extract_receive_code_常见写法() -> None:
    """中文/英文提取码写法都能解析。"""
    assert extract_receive_code("提取码：k9t2") == "k9t2"
    assert extract_receive_code("密码: ab12") == "ab12"
    assert extract_receive_code("访问码：Zx9Q") == "Zx9Q"
    assert extract_receive_code("password=abcd") == "abcd"
    assert extract_receive_code("无码内容") == ""


def test_parse_share_url_带提取码() -> None:
    """115 链接中的 password 查询参数即提取码。"""
    parsed = parse_share_url("https://115cdn.com/s/swsvxg73fwl?password=i2e8")
    assert parsed == {"cloud_type": "p115", "share_code": "swsvxg73fwl", "receive_code": "i2e8"}


def test_parse_share_url_无提取码() -> None:
    """无提取码时返回空字符串而不是异常。"""
    parsed = parse_share_url("https://pan.quark.cn/s/a158b5be345f")
    assert parsed is not None
    assert parsed["cloud_type"] == "quark"
    assert parsed["share_code"] == "a158b5be345f"
    assert parsed["receive_code"] == ""


def test_parse_share_url_非法链接() -> None:
    """非分享链接返回 None。"""
    assert parse_share_url("https://www.example.com/abc") is None
    assert parse_share_url("") is None


def test_classify_cloud_type() -> None:
    """单链接类型判断。"""
    assert classify_cloud_type("https://115.com/s/abc") == "p115"
    assert classify_cloud_type("https://pan.quark.cn/s/abc") == "quark"
    assert classify_cloud_type("https://www.example.com/x") == ""


def test_resource_item_序列化与还原() -> None:
    """ResourceItem 往返序列化后关键字段一致。"""
    item = ResourceItem(
        channel_id="Quark_Movies",
        channel_name="夸克云盘影视资源频道",
        message_id="71460",
        title="流浪地球2",
        content="4K HDR",
        pub_date="2026-08-14T02:57:28+00:00",
        tags=["#电影"],
        cloud_links=[CloudLink("quark", "https://pan.quark.cn/s/a158b5be345f", "k9t2")],
    )
    data = item.to_dict()
    assert data["url"] == "https://t.me/Quark_Movies/71460"
    assert data["cloud_types"] == ["quark"]
    restored = ResourceItem.from_dict(data)
    assert restored.channel_id == item.channel_id
    assert restored.message_id == item.message_id
    assert restored.cloud_links[0].receive_code == "k9t2"
    assert restored.to_dict() == data
