import os, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
from wxvideo_core.proxy import ProxyEngine           # noqa: E402
from wxvideo_core.runtime import CONF_DIR            # noqa: E402

e = ProxyEngine(api_port=59999, port=18081, confdir=CONF_DIR, log=lambda l, m: print("  ", l, m))
print("start:", e.start())
time.sleep(0.5)

r = subprocess.run(
    ["curl.exe", "-v", "--noproxy", "", "-x", "http://127.0.0.1:18081",
     "https://example.com", "-o", "NUL", "-m", "20"],
    capture_output=True, text=True)
print("---- curl stderr ----")
print(r.stderr[-2500:])
print("---- curl stdout ----")
print(r.stdout[-300:])
e.stop()
