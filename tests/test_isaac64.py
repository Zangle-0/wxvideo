"""WxIsaac64 密钥流与解密的单元测试（自包含，无外部样本/隐私）。

运行: PYTHONPATH=core python tests/test_isaac64.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
from wxvideo_core.isaac64 import KEYSTREAM_SIZE, WxIsaac64, decrypt  # noqa: E402

# seed=1 的密钥流基准（算法输出，非任何具体视频数据）
SEED1_HEAD16 = "e19ed5d2ca98af2da7a18d07cab39b52"
SEED1_TAIL8 = "cc20fdccf5cfab1c"


def check(name, cond):
    print(("  [OK] " if cond else "  [!!] ") + name)
    return bool(cond)


def main() -> int:
    ok = True

    ks = WxIsaac64(1).keystream(KEYSTREAM_SIZE)
    ok &= check("密钥流长度 = 131072", len(ks) == KEYSTREAM_SIZE)
    ok &= check("seed=1 头 16 字节一致", ks[:16].hex() == SEED1_HEAD16)
    ok &= check("seed=1 尾部 8 字节一致", ks[-8:].hex() == SEED1_TAIL8)
    ok &= check("两次生成结果一致（确定性）",
                WxIsaac64(1).keystream(256) == WxIsaac64(1).keystream(256))

    # 构造一个“合法 MP4 头”的明文，异或成密文，再解密应与原文一致
    plain = b"\x00\x00\x00\x20ftypisom" + b"\x00\x00\x02\x00" + os.urandom(200)
    enc = bytes(a ^ b for a, b in zip(plain, WxIsaac64(7).keystream(len(plain))))
    out = decrypt(enc, 7)
    ok &= check("解密可还原（往返一致）", out == plain)
    ok &= check("解密后含 ftyp 签名", out[4:8] == b"ftyp")

    # 只解密前 128KB：超出部分原样保留
    long_plain = os.urandom(KEYSTREAM_SIZE + 100)
    ks9 = WxIsaac64(9).keystream(KEYSTREAM_SIZE)
    long_enc = bytes(a ^ b for a, b in zip(long_plain[:KEYSTREAM_SIZE], ks9)) + long_plain[KEYSTREAM_SIZE:]
    long_out = decrypt(long_enc, 9)
    ok &= check("大于 128KB 时尾部保持原样", long_out == long_plain)

    print("== 通过 ==" if ok else "== 失败 ==")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
