# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：one-folder，把 web/dist 与依赖一起打进去。

注意：路径一律基于 SPECPATH（spec 文件所在目录），避免被按 cwd 解析。
"""
import os

from PyInstaller.utils.hooks import collect_all

SPEC_DIR = os.path.abspath(SPECPATH)                 # .../packaging
ROOT = os.path.dirname(SPEC_DIR)                     # 仓库根
CORE = os.path.join(ROOT, "core")
WEB_DIST = os.path.join(ROOT, "web", "dist")
ENTRY = os.path.join(SPEC_DIR, "entry.py")

datas = []
binaries = []
hiddenimports = []

if os.path.isdir(WEB_DIST):
    datas.append((WEB_DIST, "web/dist"))

for pkg in ["mitmproxy", "mitmproxy_rs", "webview", "uvicorn", "fastapi",
            "httpx", "pydantic", "cryptography", "pythonnet", "clr_loader"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

hiddenimports += ["wxvideo_core", "wxvideo_core.cli", "wxvideo_core.gui"]

a = Analysis(
    [ENTRY],
    pathex=[CORE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="wxvideo",
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="wxvideo")
