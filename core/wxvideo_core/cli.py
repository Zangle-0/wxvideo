"""wxvideo 命令行：doctor / decrypt / capture / gui。"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

from . import certs, netguard
from .isaac64 import KEYSTREAM_SIZE, WxIsaac64


def cmd_doctor(_args) -> int:
    print("== wxvideo doctor ==")
    ok = True

    # 解密自检
    try:
        ks = WxIsaac64(1).keystream(KEYSTREAM_SIZE)
        good = len(ks) == KEYSTREAM_SIZE
        print(f"  [{'OK' if good else '!!'}] ISAAC64 密钥流生成 ({len(ks)} bytes)")
        ok &= good
    except Exception as e:
        print(f"  [!!] ISAAC64: {e}")
        ok = False

    # 证书
    st = certs.status()
    print(f"  [{'OK' if st.get('installed') else '--'}] 根证书已信任: {st.get('installed')} (thumb={st.get('thumbprint','?')[:16]}...)")

    # 代理
    ps = netguard.status()
    print(f"  [i] 系统代理: enabled={ps['enabled']} points_to_us={ps['points_to_us']} journal={ps['armed_journal']}")
    if ps["armed_journal"] and ps["points_to_us"]:
        print("  [!] 发现遗留的代理标记，执行还原...")
        netguard.disarm()
        print("      已还原")

    # 端口
    import socket
    for p in (8080,):
        s = socket.socket()
        free = s.connect_ex(("127.0.0.1", p)) != 0
        s.close()
        print(f"  [{'OK' if free else '!'}] 端口 {p} {'可用' if free else '被占用（会自动改端口）'}")
    print("== 完成 ==" if ok else "== 有问题 ==")
    return 0 if ok else 1


def cmd_decrypt(args) -> int:
    from .isaac64 import decrypt
    enc = open(args.input, "rb").read()
    out = decrypt(enc, int(args.key))
    dest = args.output or (os.path.splitext(args.input)[0] + ".decrypted.mp4")
    with open(dest, "wb") as f:
        f.write(out)
    ok = out[4:8] == b"ftyp"
    print(f"{'OK' if ok else 'FAIL'}  头={out[:12].hex()}  -> {dest}")
    return 0 if ok else 1


def cmd_capture(args) -> int:
    from .runtime import Runtime
    rt = Runtime(proxy_port=args.port).start(with_proxy=True)
    print(f"抓包中：API http://127.0.0.1:{rt.api_port}  代理 127.0.0.1:{rt.proxy_port}")
    print("请在微信里打开/播放视频号视频；Ctrl+C 结束（会自动还原代理）")
    try:
        seen = set()
        while True:
            time.sleep(1)
            for v in rt.store.list_videos(limit=500):
                if v["object_id"] not in seen:
                    seen.add(v["object_id"])
                    print(f"  + {v['author']} | {(v['title'] or '')[:40]}")
    except KeyboardInterrupt:
        pass
    finally:
        rt.stop()
        netguard.disarm()
        print("已停止并还原代理")
    return 0


def cmd_gui(_args) -> int:
    from .gui import run_gui
    run_gui()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser("wxvideo")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="环境自检").set_defaults(func=cmd_doctor)

    d = sub.add_parser("decrypt", help="解密单个加密文件（纯 Python）")
    d.add_argument("input")
    d.add_argument("key")
    d.add_argument("output", nargs="?")
    d.set_defaults(func=cmd_decrypt)

    c = sub.add_parser("capture", help="启动抓包（无界面，前台）")
    c.add_argument("--port", type=int, default=8080)
    c.set_defaults(func=cmd_capture)

    sub.add_parser("gui", help="启动图形界面").set_defaults(func=cmd_gui)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
