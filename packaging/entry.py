"""打包入口：直接拉起图形界面（供 PyInstaller 使用）。"""
import os
import sys

# 源码运行时把 core 加入路径；打包后由 spec 的 pathex 处理
_here = os.path.dirname(os.path.abspath(__file__))
_core = os.path.join(os.path.dirname(_here), "core")
if os.path.isdir(_core):
    sys.path.insert(0, _core)

from wxvideo_core.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["gui"]))
