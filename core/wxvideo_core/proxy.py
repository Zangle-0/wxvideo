"""内嵌 mitmproxy：抓包 + 页面注入 + 记录视频请求。

与旧方案区别：**不再启动 mitmdump 子进程**，直接用 mitmproxy 库在进程内跑，
生命周期完全可控，退出/崩溃不会有孤儿进程。

注入脚本把桥接消息 POST 到本程序的本地 API（/internal/capture），由 Runtime 解析入库。
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from typing import Callable, Optional

from mitmproxy import http, options
from mitmproxy.tools import dump

INJECT_JS = r"""
<script>
(function(){
  if (window.__wxv_hooked__) return; window.__wxv_hooked__ = true;
  var ENDPOINT = "http://127.0.0.1:__API_PORT__/internal/capture";
  function send(o){ try{ o.ts = Date.now(); fetch(ENDPOINT,{method:"POST",mode:"no-cors",body:JSON.stringify(o)}).catch(function(){}); }catch(e){} }
  var INTEREST = /decodeKey|decode_key|objectDesc|object_desc|url_token|urlToken|stodownload|file_size/;
  function scan(o, where){
    if (o === undefined || o === null) return;
    var s; try { s = (typeof o === "string") ? o : JSON.stringify(o); } catch(e){ return; }
    if (s && s.length < 4000000 && INTEREST.test(s)) send({dir:"hit", where:where, data:o});
  }
  function onMsg(d, where){ if(d) scan(d, where||"xweb.resp"); }
  function hookPort(port){
    if (!port || port.__wxvPort) return !!port;
    try {
      port.__wxvPort = true;
      try { port.addEventListener("message", function(ev){ try{ onMsg(ev&&ev.data); }catch(e){} }); } catch(e){}
      var opm = port.postMessage;
      if (opm) { try { port.postMessage = function(m){ try{ if(m&&m.apiName) send({dir:"req",apiName:m.apiName,body:m.body}); }catch(e){} return opm.apply(this,arguments); }; } catch(e){} }
      try {
        var cur = port.onmessage;
        Object.defineProperty(port, "onmessage", { configurable:true, get:function(){return cur;},
          set:function(fn){ cur=function(ev){ try{ onMsg(ev&&ev.data); }catch(e){} return fn.apply(this,arguments); }; } });
      } catch(e){}
      return true;
    } catch(e){ return false; }
  }
  function hookXweb(){
    var w = window.xweb && window.xweb.worker; if (!w) return false;
    if (!w.__wxvHooked) { try{ w.__wxvHooked=true; var oc=w.connect; if(oc) w.connect=function(){ var r=oc.apply(this,arguments); setTimeout(function(){hookPort(w.port);},0); return r; }; }catch(e){} }
    hookPort(w.port); return true;
  }
  function hookBridge(){
    var b = window.WeixinJSBridge; if (!b || !b.invoke || b.__wxvHooked) return;
    try { b.__wxvHooked = true; var oi = b.invoke;
      b.invoke = function(cmd,args,cb){ if(typeof args==="function"){cb=args;args=undefined;}
        var w=function(res){ try{ scan(res,"bridge."+cmd); }catch(e){} if(cb) return cb.apply(this,arguments); };
        return oi.call(this,cmd,args,w); };
    } catch(e){}
  }
  try { window.addEventListener("message", function(ev){ try{ onMsg(ev&&ev.data,"window.msg"); }catch(e){} }); } catch(e){}
  var n=0; var t=setInterval(function(){ n++; try{ hookXweb(); hookBridge(); }catch(e){} if(n>1200) clearInterval(t); },100);
  send({dir:"hello", where:"inject", ua:navigator.userAgent, href:location.href});
})();
</script>
"""

HOSTS_OF_INTEREST = re.compile(
    r"(finder|channels|video\.qq|stodownload|wxqcloud|res\.wx)", re.I)


def build_inject_js(api_port: int) -> str:
    return INJECT_JS.replace("__API_PORT__", str(api_port))


class VxAddon:
    """mitmproxy addon：改写视频号页面注入脚本 + 记录视频请求。"""

    def __init__(self, api_port: int, log: Optional[Callable[[str, str], None]] = None,
                 on_played: Optional[Callable[[str], None]] = None,
                 on_feed_info: Optional[Callable[[str, str], None]] = None):
        self.inject_js = build_inject_js(api_port)
        self.log = log or (lambda level, msg: None)
        self.on_played = on_played or (lambda key: None)
        self.on_feed_info = on_feed_info or (lambda author, desc: None)
        self._seen_hosts: set[str] = set()
        self.video_requests: list[dict] = []
        # 真正被播放/请求过视频流的 encfilekey -> 最近一次请求时间
        self.played_ts: dict[str, float] = {}

    def _is_inject_page(self, flow: http.HTTPFlow) -> bool:
        return flow.request.pretty_host.endswith("channels.weixin.qq.com") and (
            "/web/pages/" in flow.request.path or "/finder-preview/" in flow.request.path
        )

    def request(self, flow: http.HTTPFlow) -> None:
        host = flow.request.pretty_host
        if host not in self._seen_hosts:
            self._seen_hosts.add(host)
        if self._is_inject_page(flow):
            for h in ("if-none-match", "if-modified-since"):
                if h in flow.request.headers:
                    del flow.request.headers[h]

    def response(self, flow: http.HTTPFlow) -> None:
        req, resp = flow.request, flow.response
        if resp is None:
            return
        host = req.pretty_host

        if self._is_inject_page(flow):
            ct = resp.headers.get("content-type", "")
            if ct.startswith("text/html"):
                try:
                    html = resp.get_text(strict=False)
                    idx = html.find("<head>")
                    html = (html[:idx + 6] + self.inject_js + html[idx + 6:]) if idx != -1 else (self.inject_js + html)
                    resp.set_text(html)
                    resp.headers["cache-control"] = "no-store, must-revalidate"
                    for h in ("etag", "last-modified", "expires"):
                        if h in resp.headers:
                            del resp.headers[h]
                    self.log("info", f"[inject] {req.path.split('?')[0]} patched")
                except Exception as e:
                    self.log("error", f"[inject] failed: {e}")

        # 分享链接预览接口：拿到“这条链接对应的确切标题+作者”
        if "/finder-preview/api/feed/get_feed_info" in req.path:
            try:
                body = resp.get_content(strict=False) or b""
                j = json.loads(body.decode("utf-8", "ignore"))
                data = j.get("data") or {}
                author = ((data.get("authorInfo") or {}).get("nickname") or "").strip()
                desc = ((data.get("feedInfo") or {}).get("description") or "").strip()
                if author or desc:
                    self.log("info", f"[link] {author} | {desc[:30]}")
                    self.on_feed_info(author, desc)
            except Exception:
                pass

        if "stodownload" in req.path and "/20302/" in req.path:
            self.video_requests.append({
                "url": req.pretty_url, "ts": time.time(),
                "range": req.headers.get("range"),
            })
            self.video_requests = self.video_requests[-200:]
            m = re.search(r"encfilekey=([^&]+)", req.pretty_url)
            if m:
                key = m.group(1)
                new = key not in self.played_ts
                self.played_ts[key] = time.time()
                if new:
                    try:
                        self.on_played(key)
                    except Exception:
                        pass
                if len(self.played_ts) > 3000:
                    # 只保留最近的 1000 条
                    for k in sorted(self.played_ts, key=self.played_ts.get)[:2000]:
                        self.played_ts.pop(k, None)


class ProxyEngine:
    """在**独立线程 + 独立事件循环**里运行 mitmproxy。

    与 uvicorn 的事件循环隔离，避免 DumpMaster 与 ASGI 服务器互相干扰导致代理不转发。
    """

    def __init__(self, api_port: int, port: int = 8080, confdir: str = "",
                 log: Optional[Callable[[str, str], None]] = None,
                 on_played: Optional[Callable[[str], None]] = None,
                 on_feed_info: Optional[Callable[[str, str], None]] = None):
        self.port = port
        self.confdir = confdir
        self.addon = VxAddon(api_port, log, on_played, on_feed_info)
        self.log = log or (lambda level, msg: None)
        self._master: Optional[dump.DumpMaster] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self.running = False

    def start(self, timeout: float = 10.0) -> bool:
        self._thread = threading.Thread(target=self._run, name="wxvideo-proxy", daemon=True)
        self._thread.start()
        # 等端口真正可连
        import socket
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._thread.is_alive():
                self.log("error", "[proxy] 线程已退出（启动失败）")
                return False
            s = socket.socket()
            s.settimeout(0.3)
            try:
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    self.running = True
                    self.log("info", f"[proxy] listening 127.0.0.1:{self.port}")
                    return True
            finally:
                s.close()
            time.sleep(0.2)
        self.log("error", "[proxy] 启动超时")
        return False

    def _run(self) -> None:
        async def amain():
            opts = options.Options(
                listen_host="127.0.0.1", listen_port=self.port, confdir=self.confdir,
            )
            self._master = dump.DumpMaster(opts, with_termlog=False, with_dumper=False)
            self._master.addons.add(self.addon)
            await self._master.run()

        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(amain())
        except Exception as e:
            self.log("error", f"[proxy] 异常: {e}")

    def stop(self) -> None:
        try:
            if self._master is not None and self._loop is not None and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._master.shutdown)
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.running = False
        self.log("info", "[proxy] stopped")
