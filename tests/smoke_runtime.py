import json
import sys
import time
import urllib.request
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
from wxvideo_core.runtime import Runtime  # noqa: E402

rt = Runtime().start(with_proxy=False)
print("API port:", rt.api_port)
time.sleep(1.0)
state = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{rt.api_port}/api/state", timeout=3).read())
print("state.cert.installed =", state["cert"]["installed"])
print("state.proxy_running =", state["proxy_running"])
vids = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{rt.api_port}/api/videos", timeout=3).read())
print("videos =", len(vids["videos"]))
html = urllib.request.urlopen(f"http://127.0.0.1:{rt.api_port}/", timeout=3).read().decode("utf-8", "ignore")
print("index served:", "<div id=\"app\">" in html or "assets/" in html)
rt.stop()
print("OK")
