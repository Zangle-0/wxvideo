"""系统代理安全守护（Windows 为主）。

设计目标：**任何情况下都不让用户断网**。
- arm()：记录“代理是本程序设的”+ 原值，然后设置代理。
- disarm()：还原为原值并清除记录（正常退出路径）。
- restore_if_stale()：启动时调用；若发现上次异常退出留下的标记且代理仍指向我们，则强制还原。
- is_armed()：给看门狗/UI 判断。

非 Windows 平台提供等价占位（macOS 用 networksetup 可后续补）。
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from typing import Optional

IS_WIN = platform.system() == "Windows"

APP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "wxvideo"
)
JOURNAL = os.path.join(APP_DIR, "proxy.journal")
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
BYPASS = ("localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.2*;"
          "172.30.*;172.31.*;192.168.*;<local>")


def _ensure_dir() -> None:
    os.makedirs(APP_DIR, exist_ok=True)


# --------------------------------------------------------------------------- #
# Windows 实现
# --------------------------------------------------------------------------- #
if IS_WIN:
    import ctypes
    import winreg

    INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    INTERNET_OPTION_REFRESH = 37
    INTERNET_OPTION_SETTINGS_CHANGED = 39

    def _notify() -> None:
        try:
            wininet = ctypes.windll.wininet
            wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
            wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        except Exception:
            pass

    def _read() -> dict:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as k:
            out = {}
            for name in ("ProxyEnable", "ProxyServer", "ProxyOverride"):
                try:
                    out[name] = winreg.QueryValueEx(k, name)[0]
                except FileNotFoundError:
                    out[name] = None
            return out

    def _write(enable: int, server: Optional[str], override: Optional[str]) -> None:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as k:
            winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, enable)
            if server is not None:
                winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
            if override is not None:
                winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ, override)
        _notify()

    def get_proxy() -> dict:
        return _read()

    def is_enabled() -> bool:
        return bool(_read().get("ProxyEnable"))

    def points_to_us() -> bool:
        s = (_read().get("ProxyServer") or "")
        return bool(_read().get("ProxyEnable")) and f"{PROXY_HOST}:{PROXY_PORT}" in s
else:  # 占位，避免 import 报错；后续可补 macOS networksetup
    def _notify():
        pass

    def get_proxy() -> dict:
        return {"ProxyEnable": None, "ProxyServer": None, "ProxyOverride": None}

    def is_enabled() -> bool:
        return False

    def points_to_us() -> bool:
        return False


# --------------------------------------------------------------------------- #
# 记录 / 还原
# --------------------------------------------------------------------------- #
def _load_journal() -> Optional[dict]:
    try:
        with open(JOURNAL, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_journal(data: dict) -> None:
    _ensure_dir()
    with open(JOURNAL, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _del_journal() -> None:
    try:
        os.remove(JOURNAL)
    except OSError:
        pass


def arm(port: int = PROXY_PORT, host: str = PROXY_HOST) -> dict:
    """设置系统代理，并记录原值以便还原。"""
    global PROXY_PORT, PROXY_HOST
    PROXY_HOST, PROXY_PORT = host, port
    if not IS_WIN:
        return {"ok": False, "reason": f"暂不支持 {platform.system()}"}
    original = get_proxy()
    _save_journal({"armed": True, "host": host, "port": port, "original": original})
    _write(1, f"{host}:{port}", BYPASS)
    return {"ok": True, "original": original}


def disarm() -> dict:
    """还原代理（优先还原到 journal 里的原值）。"""
    if not IS_WIN:
        return {"ok": True}
    j = _load_journal()
    if j and j.get("original"):
        o = j["original"]
        _write(int(o.get("ProxyEnable") or 0), o.get("ProxyServer"), o.get("ProxyOverride"))
    else:
        _write(0, None, None)
    _del_journal()
    return {"ok": True}


def restore_if_stale() -> bool:
    """启动自检：上次异常退出（有 journal 且代理仍指向我们）→ 还原。返回是否做了还原。"""
    if not IS_WIN:
        return False
    j = _load_journal()
    if j and j.get("armed") and points_to_us():
        disarm()
        return True
    if j and not points_to_us():
        _del_journal()  # 标记过期，清掉
    return False


def status() -> dict:
    return {
        "enabled": is_enabled(),
        "points_to_us": points_to_us(),
        "armed_journal": bool(_load_journal()),
        "proxy": get_proxy(),
    }
