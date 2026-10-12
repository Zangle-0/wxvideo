"""mitmproxy 根证书管理：生成 / 安装到“当前用户-受信任的根” / 检测 / 卸载。

不需要管理员：装到 CurrentUser 的 Root 存储即可（微信以当前用户运行）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from mitmproxy import certs as mtcerts

APP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "wxvideo"
)
CONF_DIR = os.path.join(APP_DIR, "mitmproxy")
# 必须与 mitmproxy 运行时的默认 basename 一致，否则它会在运行时另生成一张未受信任的 CA
BASENAME = "mitmproxy"


def ca_cer_path() -> str:
    return os.path.join(CONF_DIR, f"{BASENAME}-ca-cert.cer")


def ensure_ca() -> str:
    """确保 CA 存在，返回 .cer(DER) 路径。mitmproxy 会写出 <basename>-ca-cert.cer。"""
    os.makedirs(CONF_DIR, exist_ok=True)
    if not os.path.exists(ca_cer_path()):
        mtcerts.CertStore.from_store(CONF_DIR, BASENAME, 2048)
    if not os.path.exists(ca_cer_path()):
        # 兜底：从 pem 导出 der
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        pem = os.path.join(CONF_DIR, f"{BASENAME}-ca-cert.pem")
        with open(pem, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        with open(ca_cer_path(), "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.DER))
    return ca_cer_path()


def thumbprint() -> str:
    """返回 CA 的 SHA1 指纹（无空格大写）。"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    ensure_ca()
    with open(ca_cer_path(), "rb") as f:
        data = f.read()
    try:
        cert = x509.load_der_x509_certificate(data)
    except ValueError:
        cert = x509.load_pem_x509_certificate(data)
    return cert.fingerprint(hashes.SHA1()).hex().upper()


def _certutil(*args: str) -> str:
    """调用 certutil，并隐藏控制台窗口（GUI 程序下避免黑框一闪）。"""
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kw["startupinfo"] = si
        except Exception:
            pass
    r = subprocess.run(["certutil", *args], capture_output=True, text=True,
                       errors="ignore", **kw)
    return (r.stdout or "") + (r.stderr or "")


# 缓存“是否已安装”，避免每次 /api/state 都去调 certutil
_cache: dict = {"installed": None, "ts": 0.0}
_CACHE_TTL = 20.0


def is_installed(force: bool = False) -> bool:
    now = time.time()
    if not force and _cache["installed"] is not None and now - _cache["ts"] < _CACHE_TTL:
        return _cache["installed"]
    tp = thumbprint().replace(" ", "")
    out = _certutil("-user", "-store", "Root")
    val = tp.lower() in out.replace(" ", "").lower()
    _cache.update(installed=val, ts=now)
    return val


def install() -> dict:
    cer = ensure_ca()
    tp = thumbprint()
    if is_installed():
        return {"ok": True, "thumbprint": tp, "path": cer, "raw": "already installed"}
    # 清理同名旧证书，避免多份
    _certutil("-user", "-delstore", "Root", tp)  # 幂等
    out = _certutil("-user", "-addstore", "Root", cer)
    ok = is_installed(force=True)
    _cache.update(installed=ok, ts=time.time())
    return {"ok": ok, "thumbprint": tp, "path": cer, "raw": out.strip()[-400:]}


def uninstall() -> dict:
    tp = thumbprint()
    out = _certutil("-user", "-delstore", "Root", tp)
    ok = not is_installed(force=True)
    _cache.update(installed=not ok, ts=time.time())
    return {"ok": ok, "thumbprint": tp, "raw": out.strip()[-400:]}


def status() -> dict:
    try:
        tp = thumbprint()
        return {"exists": True, "installed": is_installed(), "thumbprint": tp, "path": ca_cer_path()}
    except Exception as e:
        return {"exists": False, "installed": False, "error": str(e)}
