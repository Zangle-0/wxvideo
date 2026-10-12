#!/usr/bin/env python3
"""开发用入口：python run.py [doctor|decrypt|capture|gui]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from wxvideo_core.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
