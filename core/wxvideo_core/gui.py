"""pywebview 图形界面壳：加载本地 Runtime 的 Web UI。"""

from __future__ import annotations

import os

import webview

from .runtime import Runtime

WINDOW_TITLE = "wxvideo · 微信视频号下载器"


def run_gui() -> None:
    # 只先起 API（不自动开代理）；是否监听由界面上的开关控制。
    rt = Runtime().start(with_proxy=False)
    url = f"http://127.0.0.1:{rt.api_port}/"
    window = webview.create_window(
        WINDOW_TITLE,
        url,
        width=1120,
        height=760,
        min_size=(900, 600),
        text_select=False,
    )
    try:
        webview.start()
    finally:
        # 退出时一定还原代理，避免断网
        rt.stop()
