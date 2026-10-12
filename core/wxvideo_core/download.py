"""流式下载 + 解密：边下边对前 128KB 做 ISAAC64 XOR，直接落成可播放 MP4。"""

from __future__ import annotations

import os
from typing import Callable, Optional

import httpx

from .isaac64 import KEYSTREAM_SIZE, WxIsaac64

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 "
      "MicroMessenger/7.0.20.1781 WindowsWechat")
HEADERS = {"User-Agent": UA, "Referer": "https://channels.weixin.qq.com/"}


def safe_filename(name: str, maxlen: int = 80) -> str:
    import re
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name or "").strip(" ._")
    return (name[:maxlen] or "video")


async def download_decrypt(
    url: str,
    decode_key: str,
    dest_path: str,
    *,
    on_progress: Optional[Callable[[int, int], None]] = None,
    timeout: float = 60.0,
) -> dict:
    """下载并解密到 dest_path。返回 {'bytes','total','ok'}。"""
    ks = WxIsaac64(int(decode_key)).keystream(KEYSTREAM_SIZE)
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    tmp = dest_path + ".part"
    written = 0
    total = 0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=HEADERS) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    if written < KEYSTREAM_SIZE and chunk:
                        n = min(len(chunk), KEYSTREAM_SIZE - written)
                        chunk = bytes(b ^ ks[written + i] for i, b in enumerate(chunk[:n])) + chunk[n:]
                    f.write(chunk)
                    written += len(chunk)
                    if on_progress:
                        try:
                            on_progress(written, total)
                        except Exception:
                            pass
    # 校验
    ok = False
    try:
        with open(tmp, "rb") as f:
            head = f.read(12)
        ok = head[4:8] == b"ftyp"
    except Exception:
        ok = False
    if not ok:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("解密校验失败：输出不是合法 MP4（可能 decode_key 已过期，请重新抓取）")
    os.replace(tmp, dest_path)
    return {"bytes": written, "total": total, "ok": True, "path": dest_path}
