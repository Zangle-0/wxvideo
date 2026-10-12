"""Runtime：把代理、本地 API、存储、代理守护编排到一起。

一个后台线程跑一个 asyncio 事件循环，循环内同时驻留：
  - ProxyEngine(mitmproxy 内嵌)
  - uvicorn 提供本地 HTTP + WebSocket
事件通过 WebSocket 推给 UI；GUI（pywebview）只是这个 Runtime 的壳。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import sys
import threading
import time
from typing import Any, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from . import certs, netguard
from .download import download_decrypt, safe_filename
from .isaac64 import KEYSTREAM_SIZE
from .media import is_detail_payload, parse_bridge_payload
from .proxy import ProxyEngine
from .store import Store

APP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "wxvideo"
)
CONF_DIR = os.path.join(APP_DIR, "mitmproxy")


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def web_dist_dir() -> str:
    """定位前端构建产物目录，兼容源码运行与 PyInstaller 打包。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        for cand in (os.path.join(base, "web", "dist"),
                     os.path.join(os.path.dirname(sys.executable), "web", "dist")):
            if os.path.isdir(cand):
                return cand
        return os.path.join(base, "web", "dist")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "web", "dist")


class Runtime:
    def __init__(self, proxy_port: int = 8080, api_port: int = 0,
                 download_dir: Optional[str] = None):
        os.makedirs(APP_DIR, exist_ok=True)
        self.store = Store()
        self.download_dir = download_dir or self.store.get_setting(
            "download_dir", os.path.join(os.path.expanduser("~"), "Downloads", "wxvideo"))
        self.proxy_port = proxy_port
        self.api_port = api_port or free_port()
        self.proxy: Optional[ProxyEngine] = None
        self.server = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ws: set[WebSocket] = set()
        self._tasks: set[asyncio.Task] = set()
        self.session_started_at: Optional[float] = None
        self.focused: dict[str, float] = {}   # 正在查看过的视频（来自详情/评论请求）
        self.target: Optional[dict] = None    # 链接定向：待锁定/已锁定的目标
        self.app = self._build_app()

    # ------------------------------------------------------------------ #
    def log(self, level: str, msg: str) -> None:
        try:
            self.store.log(level, msg)
        except Exception:
            pass
        self.emit({"type": "log", "level": level, "msg": msg, "ts": time.time()})

    def emit(self, event: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._broadcast, event)

    def _broadcast(self, event: dict) -> None:
        data = json.dumps(event, ensure_ascii=False)
        dead = []
        for ws in list(self._ws):
            try:
                asyncio.ensure_future(ws.send_text(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws.discard(ws)

    # ------------------------------------------------------------------ #
    def _build_app(self) -> FastAPI:
        app = FastAPI(title="wxvideo", docs_url=None, redoc_url=None)

        @app.post("/internal/capture")
        async def internal_capture(req: Request):
            raw = (await req.body()).decode("utf-8", "ignore")
            try:
                obj = json.loads(raw)
            except Exception:
                return JSONResponse({"ok": False})
            if obj.get("dir") == "hit":
                data = obj.get("data") or {}
                focused = is_detail_payload(data)
                for v in parse_bridge_payload(data):
                    self._on_video(v, focused=focused)
            return JSONResponse({"ok": True})

        @app.get("/api/state")
        async def state():
            return {
                "api_port": self.api_port,
                "proxy_port": self.proxy_port,
                "proxy_running": bool(self.proxy and self.proxy.running),
                "proxy": netguard.status(),
                "cert": certs.status(),
                "download_dir": self.download_dir,
                "session_started_at": self.session_started_at,
                "target": self.target,
                "count": len(self.store.list_videos(limit=10000)),
            }

        def _encfilekey(url: str) -> Optional[str]:
            m = re.search(r"encfilekey=([^&]+)", url or "")
            return m.group(1) if m else None

        @app.get("/api/videos")
        async def videos(limit: int = 200, played: int = 0):
            rows = self.store.list_videos(limit=limit)
            pts = self.proxy.addon.played_ts if self.proxy else {}
            out = []
            for v in rows:
                cap = self.store.latest_capture(v["object_id"])
                ek = _encfilekey(cap["url"]) if cap else None
                lp = float(pts.get(ek, 0)) if ek else 0.0
                v["played"] = lp > 0
                v["last_played_at"] = lp
                v["focused"] = v["object_id"] in self.focused
                v["target"] = bool(self.target and self.target.get("object_id") == v["object_id"])
                v["captured_at"] = cap["captured_at"] if cap else None
                if played and not (v["played"] or v["focused"] or v["target"]):
                    continue
                out.append(v)
            # 链接目标最前，其次“当前查看的”，再次最近播放，最后抓取时间
            out.sort(key=lambda x: (x["target"], x["focused"], x["last_played_at"], x.get("captured_at") or 0), reverse=True)
            return {"videos": out}

        @app.post("/api/download")
        async def api_download(payload: dict):
            oid = str(payload.get("object_id") or "")
            fmt = payload.get("fmt")
            if not oid:
                return JSONResponse({"ok": False, "error": "object_id required"}, status_code=400)
            t = asyncio.ensure_future(self.download(oid, fmt))
            self._tasks.add(t)
            t.add_done_callback(self._tasks.discard)
            return {"ok": True}

        @app.post("/api/proxy/start")
        async def api_start():
            await self.start_proxy()
            return {"ok": True}

        @app.post("/api/proxy/stop")
        async def api_stop():
            await self.stop_proxy()
            return {"ok": True}

        @app.post("/api/cert/install")
        async def api_cert_install():
            r = certs.install()
            self.log("info", f"证书安装: {'成功' if r.get('ok') else '失败'}")
            return r

        @app.post("/api/cert/uninstall")
        async def api_cert_uninstall():
            return certs.uninstall()

        @app.post("/api/netguard/restore")
        async def api_restore():
            netguard.disarm()
            if self.proxy:
                self.proxy.stop()
            return {"ok": True}

        @app.post("/api/settings")
        async def api_settings(payload: dict):
            if "download_dir" in payload and payload["download_dir"]:
                self.download_dir = payload["download_dir"]
                self.store.set_setting("download_dir", self.download_dir)
            return {"ok": True, "download_dir": self.download_dir}

        @app.post("/api/target")
        async def api_target(payload: dict):
            link = str(payload.get("link") or "").strip()
            m = re.search(r"/sph/([A-Za-z0-9_-]+)", link)
            short = m.group(1) if m else ""
            self.target = {"link": link, "short_id": short, "author": "", "title": "", "object_id": None}
            self.log("info", f"已设置链接目标：{short or link}（请在微信打开它）")
            self.emit({"type": "target", "object_id": None, "pending": True})
            return {"ok": True, "short_id": short}

        @app.post("/api/doctor")
        async def api_doctor():
            lines = [
                f"ISAAC64 自检: OK ({KEYSTREAM_SIZE} bytes)",
                f"证书: {certs.status()}",
                f"代理: {netguard.status()}",
                f"API 端口: {self.api_port} / 代理端口: {self.proxy_port}",
                f"视频数: {len(self.store.list_videos(limit=100000))}",
            ]
            return {"report": " | ".join(lines)}

        @app.websocket("/ws")
        async def ws(websocket: WebSocket):
            await websocket.accept()
            self._ws.add(websocket)
            try:
                await websocket.send_text(json.dumps(
                    {"type": "hello", "api_port": self.api_port, "proxy_port": self.proxy_port}))
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                self._ws.discard(websocket)

        # 托管前端构建产物（web/dist）；放在最后，避免遮蔽上面的 API
        try:
            from fastapi.staticfiles import StaticFiles
            dist = web_dist_dir()
            if os.path.isdir(dist):
                app.mount("/", StaticFiles(directory=dist, html=True), name="web")
            else:
                self.log("error", f"前端目录缺失：{dist}")
        except Exception as e:
            self.log("error", f"挂载前端失败：{e}")

        return app

    # ------------------------------------------------------------------ #
    @staticmethod
    def _norm(s: str) -> str:
        return re.sub(r"[\s#＃]+", "", s or "")

    def _match_video(self, author: str, desc: str) -> Optional[dict]:
        nd = self._norm(desc)
        if not nd:
            return None
        best, best_score = None, 0
        for r in self.store.list_videos(limit=100000):
            rd = self._norm(r.get("title") or "")
            if not rd:
                continue
            if nd in rd or rd in nd:
                score = min(len(nd), len(rd))
                if score > best_score:
                    best, best_score = r, score
        return best

    def _on_feed_info(self, author: str, desc: str) -> None:
        """代理线程回调：链接预览信息到了，精确匹配并锁定。"""
        t = self.target or {}
        t.update({"author": author, "title": desc})
        v = self._match_video(author, desc)
        if v:
            t["object_id"] = v["object_id"]
            self.target = t
            self.log("info", f"[link] 已锁定目标：{v['author']} | {v['title'][:30]}")
            self.emit({"type": "target", "object_id": v["object_id"],
                       "author": v["author"], "title": v["title"]})
        else:
            self.target = t
            self.log("warn", f"[link] 收到预览（{author} | {desc[:20]}）但库里暂无匹配")
            self.emit({"type": "target", "object_id": None, "author": author, "title": desc})

    # ------------------------------------------------------------------ #
    def _on_video(self, v, focused: bool = False) -> None:
        self.store.upsert_video(
            object_id=v.object_id, author=v.author, title=v.title,
            duration_ms=v.duration_ms, cover_url=v.cover_url, specs=v.specs)
        self.store.add_capture(
            object_id=v.object_id, url=v.url, url_token=v.url_token,
            decode_key=v.decode_key or "", file_size=v.file_size)
        if focused:
            self.focused[v.object_id] = time.time()
            self.emit({"type": "focused", "object_id": v.object_id})
        self.emit({"type": "video", "video": {
            "object_id": v.object_id, "author": v.author, "title": v.title,
            "duration_ms": v.duration_ms, "cover_url": v.cover_url,
            "file_size": v.file_size, "formats": v.spec_formats(),
            "captured_at": time.time(),
        }})
        self.log("info", f"[captured]{'★' if focused else ''} {v.author} | {v.title[:30]}")

    # ------------------------------------------------------------------ #
    async def start_proxy(self) -> None:
        if self.proxy and self.proxy.running:
            return
        self.session_started_at = time.time()

        def _played(_key: str) -> None:
            self.emit({"type": "played"})

        self.proxy = ProxyEngine(self.api_port, self.proxy_port, CONF_DIR, self.log,
                                 _played, self._on_feed_info)
        ok = self.proxy.start()
        if not ok:
            self.log("error", "抓包启动失败")
            self.emit({"type": "proxy", "running": False})
            return
        netguard.arm(self.proxy_port)
        self.log("info", "抓包已开启（系统代理已指向本程序）")
        self.emit({"type": "proxy", "running": True, "session_started_at": self.session_started_at})

    async def stop_proxy(self) -> None:
        if self.proxy:
            self.proxy.stop()
        netguard.disarm()
        self.log("info", "抓包已关闭（系统代理已还原）")
        self.emit({"type": "proxy", "running": False})

    async def download(self, object_id: str, fmt: Optional[str] = None) -> None:
        cap = self.store.latest_capture(object_id)
        v = self.store.get_video(object_id) or {}
        if not cap:
            self.log("error", "没有可用抓取记录（请先播放该视频以获取新链接）")
            self.emit({"type": "download", "object_id": object_id, "status": "error",
                       "error": "no-capture"})
            return
        url = cap["url"] + (cap["url_token"] or "")
        if cap["url_token"] and cap["url_token"][0] not in "&?":
            url = cap["url"] + "&" + cap["url_token"]
        if fmt:
            url += f"&X-snsvideoflag={fmt}"
        name = safe_filename(v.get("title") or object_id)
        dest = os.path.join(self.download_dir, f"{name}_{object_id}{('_' + fmt) if fmt else ''}.mp4")
        dl_id = self.store.set_download(object_id=object_id, fmt=fmt or "", path=dest, status="downloading")
        self.emit({"type": "download", "object_id": object_id, "status": "downloading", "path": dest})

        def prog(written: int, total: int) -> None:
            self.store.update_download(dl_id, bytes=written, status="downloading")
            self.emit({"type": "progress", "object_id": object_id,
                       "bytes": written, "total": total})

        try:
            r = await download_decrypt(url, str(cap["decode_key"]), dest, on_progress=prog)
            self.store.update_download(dl_id, bytes=r["bytes"], status="done", path=dest)
            self.emit({"type": "download", "object_id": object_id, "status": "done", "path": dest})
            self.log("info", f"下载完成 -> {dest}")
        except Exception as e:
            self.store.update_download(dl_id, status="error")
            self.emit({"type": "download", "object_id": object_id, "status": "error", "error": str(e)})
            self.log("error", f"下载失败: {e}")

    # ------------------------------------------------------------------ #
    async def _serve(self) -> None:
        import uvicorn
        config = uvicorn.Config(self.app, host="127.0.0.1", port=self.api_port,
                                log_level="warning", loop="asyncio", lifespan="off")
        self.server = uvicorn.Server(config)
        await self.server.serve()

    def start(self, with_proxy: bool = True) -> "Runtime":
        """在后台线程启动事件循环 + API(+代理)。"""
        async def main():
            self._loop = asyncio.get_running_loop()
            # 启动自检：上次异常退出留下的代理标记
            if netguard.restore_if_stale():
                self.log("warn", "检测到上次异常退出，已自动还原系统代理")
            await self._serve() if not with_proxy else await asyncio.gather(
                self._serve(), self._start_proxy_then_idle())

        async def _start_proxy_then_idle():
            await self.start_proxy()
            while True:
                await asyncio.sleep(3600)

        def runner():
            asyncio.run(main())

        self._thread = threading.Thread(target=runner, name="wxvideo-runtime", daemon=True)
        self._thread.start()
        # 等 API 起来
        for _ in range(100):
            time.sleep(0.1)
            try:
                import urllib.request
                urllib.request.urlopen(f"http://127.0.0.1:{self.api_port}/api/state", timeout=1)
                break
            except Exception:
                continue
        return self

    def stop(self) -> None:
        # 关键：无论如何先还原代理，避免断网
        netguard.disarm()
        if self._loop and not self._loop.is_closed():
            if self.server:
                self.server.should_exit = True
