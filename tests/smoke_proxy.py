import os, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
from wxvideo_core.proxy import ProxyEngine           # noqa: E402
from wxvideo_core.runtime import CONF_DIR            # noqa: E402

e = ProxyEngine(api_port=59999, port=18080, confdir=CONF_DIR, log=lambda l, m: print("  ", l, m))
print("start:", e.start())
time.sleep(0.5)


def curl(url):
    r = subprocess.run(
        ["curl.exe", "-s", "--ssl-no-revoke", "--noproxy", "", "-x", "http://127.0.0.1:18080", url,
         "-o", "NUL", "-m", "20", "-w", "%{http_code} %{time_total}s"],
        capture_output=True, text=True)
    return r.stdout.strip()


print("example.com          ->", curl("https://example.com"))
print("res.wx.qq.com        ->", curl("https://res.wx.qq.com/open/libs/weui/2.4.1/weui.min.css"))
print("channels.weixin.qq.com ->", curl("https://channels.weixin.qq.com/web/pages/feed"))
e.stop()
