"""从注入回传的 bridge 响应里解析视频元数据。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WxVideo:
    object_id: str = ""
    author: str = ""
    title: str = ""
    duration_ms: int = 0
    cover_url: str = ""
    url: str = ""
    url_token: str = ""
    decode_key: Optional[str] = None
    file_size: int = 0
    specs: list[dict] = field(default_factory=list)

    @property
    def full_url(self) -> str:
        tok = self.url_token or ""
        if not tok:
            return self.url
        if tok[0] in "&?":
            return self.url + tok
        return self.url + "&" + tok

    def spec_formats(self) -> list[str]:
        return [s.get("fmt") for s in self.specs if s.get("fmt")]


def _specs(media: dict) -> list[dict]:
    out = []
    for s in media.get("spec") or []:
        if isinstance(s, dict):
            out.append({
                "fmt": s.get("file_format"),
                "codec": s.get("coding_format"),
                "w": s.get("width"),
                "h": s.get("height"),
                "br": s.get("video_bitrate"),
                "q": s.get("quality_score"),
            })
    return out


def _media_to_video(obj: dict) -> Optional[WxVideo]:
    od = obj.get("object_desc") or {}
    media = od.get("media") or []
    if not media:
        return None
    m = media[0]
    dk = m.get("decode_key") or m.get("decodeKey")
    url = (m.get("url") or "").strip()
    if not url or dk is None:
        return None
    # video_play_len 单位是“秒”；duration_ms（若有）才是毫秒
    vpl = m.get("video_play_len")
    dur_ms = int(vpl) * 1000 if vpl else int(m.get("duration_ms") or 0)
    return WxVideo(
        object_id=str(obj.get("id") or ""),
        author=(obj.get("nickname") or "").strip(),
        title=(od.get("description") or "").strip(),
        duration_ms=dur_ms,
        cover_url=(m.get("thumb_url") or m.get("cover_url") or "").strip(),
        url=url,
        url_token=(m.get("url_token") or "").strip(),
        decode_key=str(dk),
        file_size=int(m.get("file_size") or 0),
        specs=_specs(m),
    )


def is_detail_payload(payload: Any) -> bool:
    """判断这份 bridge 数据是不是“正在查看的那条”的详情响应。

    关键：详情响应里 comment_info 是**非空**的真评论列表；而信息流里每张卡片的
    预览是空列表。用它可精确锁定用户点开的那条。
    """
    jr = (payload or {}).get("jsapi_resp") or {}
    rj = jr.get("resp_json")
    if not rj:
        return False
    try:
        inner = json.loads(rj)
    except Exception:
        return False
    ci = inner.get("comment_info")
    return isinstance(ci, list) and len(ci) > 0


def parse_bridge_payload(payload: Any) -> list[WxVideo]:
    """payload 是注入脚本回传的 {dir:'hit', data:{...jsapi_resp...}} 里的 data。"""
    jr = (payload or {}).get("jsapi_resp") or {}
    rj = jr.get("resp_json")
    if not rj:
        return []
    try:
        inner = json.loads(rj)
    except Exception:
        return []
    objs = inner.get("object")
    objs = objs if isinstance(objs, list) else ([objs] if isinstance(objs, dict) else [])
    out = []
    for obj in objs:
        v = _media_to_video(obj or {})
        if v:
            out.append(v)
    return out
