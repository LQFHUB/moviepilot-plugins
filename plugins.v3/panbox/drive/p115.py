"""115 网盘驱动（自研 HTTP 实现，不引入第三方 SDK）。

接口事实来源：115 网页版接口 ``https://webapi.115.com``，沿用其小程序端请求头。
仅实现本插件需要的能力：Cookie 校验、分享信息解析、目录列举、转存。

设计取舍：不依赖 ``p115client`` 等第三方库，避免向 MoviePilot 共享 Python 环境
引入新依赖（用户环境已有插件对依赖做过钉版，新增依赖有冲突风险）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.sdk.network import RequestUtils

from ..core.models import parse_share_url

__all__ = ["P115Client", "P115Error"]

API_BASE = "https://webapi.115.com"

#: 沿用 115 小程序端 UA 与 Referer，网页版接口依赖该组合
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 "
    "MicroMessenger/6.8.0(0x16080000) NetType/WIFI MiniProgramEnv/Mac "
    "MacWechat/WMPF MacWechat/3.8.9(0x13080910) XWEB/1227"
)
_DEFAULT_REFERER = "https://servicewechat.com/wx2c744c010a61b0fa/94/page-frame.html"


class P115Error(Exception):
    """115 接口调用失败。"""


class P115Client:
    """115 网盘客户端。"""

    def __init__(
        self,
        cookie: str,
        timeout: int = 20,
        proxy: Optional[str] = None,
    ) -> None:
        """初始化客户端。

        :param cookie: 115 网页版 Cookie 字符串
        :param timeout: 请求超时秒数
        :param proxy: 可选代理地址
        """
        self._cookie = (cookie or "").strip()
        self._timeout = timeout or 20
        self._proxies = {"http": proxy, "https": proxy} if proxy else None

    @property
    def available(self) -> bool:
        """是否已配置 Cookie。"""
        return bool(self._cookie)

    def _client(self) -> RequestUtils:
        """构造带 115 专用请求头的宿主 HTTP 客户端。

        注意：``RequestUtils`` 在显式传入 ``headers`` 时不会再套用 ``ua`` 参数，
        因此 User-Agent 必须写进 ``headers`` 本身。
        """
        return RequestUtils(
            headers={
                "Host": "webapi.115.com",
                "User-Agent": _DEFAULT_UA,
                "xweb_xhr": "1",
                "Accept": "*/*",
                "Referer": _DEFAULT_REFERER,
                "Cookie": self._cookie,
            },
            timeout=self._timeout,
            proxies=self._proxies,
            verify=True,
        )

    # ------------------------------------------------------------------ 校验
    def check(self) -> Dict[str, Any]:
        """校验 Cookie 是否可用。

        :return: 含 ``ok`` 与 ``message`` 的字典
        """
        if not self.available:
            return {"ok": False, "message": "未配置 115 Cookie"}
        try:
            self.folders("0")
        except P115Error as error:
            return {"ok": False, "message": str(error)}
        return {"ok": True, "message": "115 Cookie 可用"}

    # ------------------------------------------------------------------ 目录
    def folders(self, cid: str = "0") -> List[Dict[str, str]]:
        """列举指定目录下的子目录。

        :param cid: 目录 ID，根目录为 ``0``
        :return: 目录列表，元素含 ``cid`` 与 ``name``
        """
        client = self._client()
        response = client.get_res(
            f"{API_BASE}/files",
            params={
                "aid": 1,
                "cid": cid or "0",
                "o": "user_ptime",
                "asc": 1,
                "offset": 0,
                "show_dir": 1,
                "limit": 100,
                "type": 0,
                "format": "json",
                "star": 0,
                "suffix": "",
                "natsort": 0,
                "snap": 0,
                "record_open_time": 1,
                "fc_mix": 0,
            },
        )
        if response is None:
            raise P115Error("115 目录接口无响应")
        try:
            payload = response.json()
        except Exception as error:  # noqa: BLE001 - 兼容非 JSON 响应（通常是登录页）
            raise P115Error("115 返回非 JSON 内容，Cookie 可能已失效") from error
        if not payload.get("state"):
            raise P115Error(str(payload.get("error") or "115 Cookie 无效或已过期"))
        folders = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            if item.get("cid") and item.get("ns"):
                folders.append({"cid": str(item.get("cid")), "name": str(item.get("n") or "")})
        return folders

    # ------------------------------------------------------------------ 分享
    def share_info(self, share_code: str, receive_code: str = "") -> List[Dict[str, Any]]:
        """解析 115 分享链接中的文件清单。

        :param share_code: 分享码
        :param receive_code: 提取码，可为空
        :return: 文件列表，元素含 ``file_id`` / ``file_name`` / ``file_size``
        """
        client = self._client()
        response = client.get_res(
            f"{API_BASE}/share/snap",
            params={
                "share_code": share_code,
                "receive_code": receive_code or "",
                "offset": 0,
                "limit": 100,
                "cid": "",
            },
        )
        if response is None:
            raise P115Error("115 分享接口无响应")
        try:
            payload = response.json()
        except Exception as error:  # noqa: BLE001
            raise P115Error("115 分享接口返回非 JSON 内容") from error
        data = payload.get("data") or {}
        files = data.get("list") or []
        if not payload.get("state") or not files:
            raise P115Error(str(payload.get("error") or "未获取到分享文件，提取码可能不正确"))
        return [
            {
                "file_id": str(item.get("cid") or ""),
                "file_name": str(item.get("n") or ""),
                "file_size": item.get("s") or 0,
            }
            for item in files
            if isinstance(item, dict)
        ]

    # ------------------------------------------------------------------ 转存
    def save(
        self,
        share_code: str,
        receive_code: str = "",
        file_id: str = "",
        cid: str = "0",
    ) -> Dict[str, Any]:
        """把分享文件转存到指定目录。

        :param share_code: 分享码
        :param receive_code: 提取码
        :param file_id: 分享内的文件 ID
        :param cid: 目标目录 ID
        :return: 含 ``ok`` 与 ``message`` 的字典
        """
        client = self._client()
        response = client.post(
            f"{API_BASE}/share/receive",
            data={
                "cid": cid or "0",
                "share_code": share_code,
                "receive_code": receive_code or "",
                "file_id": file_id,
            },
        )
        if response is None:
            raise P115Error("115 转存接口无响应")
        try:
            payload = response.json()
        except Exception as error:  # noqa: BLE001
            raise P115Error("115 转存接口返回非 JSON 内容") from error
        if not payload.get("state"):
            raise P115Error(str(payload.get("error") or "转存失败"))
        return {"ok": True, "message": str(payload.get("error") or "转存成功"), "data": payload.get("data")}

    # ------------------------------------------------------------------ 便捷
    def transfer_url(self, url: str, cid: str = "0") -> Dict[str, Any]:
        """按分享链接直接转存（自动解析分享码、提取码与文件）。

        :param url: 网盘分享链接
        :param cid: 目标目录 ID
        :return: 含 ``ok`` / ``message`` / ``files`` 的字典
        """
        parsed = parse_share_url(url)
        if not parsed or parsed.get("cloud_type") != "p115":
            return {"ok": False, "message": "不是可识别的 115 分享链接"}
        files = self.share_info(parsed["share_code"], parsed["receive_code"])
        if not files:
            return {"ok": False, "message": "分享内没有可转存的文件"}
        first = files[0]
        result = self.save(
            share_code=parsed["share_code"],
            receive_code=parsed["receive_code"],
            file_id=first["file_id"],
            cid=cid,
        )
        return {
            "ok": result["ok"],
            "message": result["message"],
            "share_code": parsed["share_code"],
            "file_name": first["file_name"],
            "files": files,
        }
