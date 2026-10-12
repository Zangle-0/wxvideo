"""WxIsaac64 —— 微信视频号密钥流生成（纯 Python，无 wasm / 无 JS / 无 Node）。

算法来源：Hanson/WechatSphDecrypt 的 ISAAC64 变种（Bob Jenkins ISAAC64）。
    种子 = decode_key（uint64），其余 Seed 置 0；
    密钥流按“每随机数 8 字节大端”顺序拼接；
    只加密视频前 128KB（131072 字节），其余为明文。

规范：所有运算按 uint64 取模 2^64，移位为逻辑移位。
"""

from __future__ import annotations

MASK = 0xFFFFFFFFFFFFFFFF
GOLDEN = 0x9E3779B97F4A7C13
KEYSTREAM_SIZE = 131072  # 2^17，微信只加密前 128KB


def _mix(a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: int):
    a = (a - e) & MASK
    f ^= (h >> 9)
    h = (h + a) & MASK
    b = (b - f) & MASK
    g ^= (a << 9) & MASK
    a = (a + b) & MASK
    c = (c - g) & MASK
    h ^= (b >> 23)
    b = (b + c) & MASK
    d = (d - h) & MASK
    a ^= (c << 15) & MASK
    c = (c + d) & MASK
    e = (e - a) & MASK
    b ^= (d >> 14)
    d = (d + e) & MASK
    f = (f - b) & MASK
    c ^= (e << 20) & MASK
    e = (e + f) & MASK
    g = (g - c) & MASK
    d ^= (f >> 17)
    f = (f + g) & MASK
    h = (h - d) & MASK
    e ^= (g << 14) & MASK
    g = (g + h) & MASK
    return a, b, c, d, e, f, g, h


class WxIsaac64:
    def __init__(self, seed: int):
        self.seed = [0] * 256
        self.mm = [0] * 256
        self.aa = 0
        self.bb = 0
        self.cc = 0
        self.rand_cnt = 255
        self.seed[0] = seed & MASK
        self._init()

    def _init(self) -> None:
        a = b = c = d = e = f = g = h = GOLDEN
        for _ in range(4):
            a, b, c, d, e, f, g, h = _mix(a, b, c, d, e, f, g, h)
        s = self.seed
        m = self.mm
        for i in range(0, 256, 8):
            a = (a + s[i]) & MASK
            b = (b + s[i + 1]) & MASK
            c = (c + s[i + 2]) & MASK
            d = (d + s[i + 3]) & MASK
            e = (e + s[i + 4]) & MASK
            f = (f + s[i + 5]) & MASK
            g = (g + s[i + 6]) & MASK
            h = (h + s[i + 7]) & MASK
            a, b, c, d, e, f, g, h = _mix(a, b, c, d, e, f, g, h)
            m[i], m[i + 1], m[i + 2], m[i + 3] = a, b, c, d
            m[i + 4], m[i + 5], m[i + 6], m[i + 7] = e, f, g, h
        for i in range(0, 256, 8):
            a = (a + m[i]) & MASK
            b = (b + m[i + 1]) & MASK
            c = (c + m[i + 2]) & MASK
            d = (d + m[i + 3]) & MASK
            e = (e + m[i + 4]) & MASK
            f = (f + m[i + 5]) & MASK
            g = (g + m[i + 6]) & MASK
            h = (h + m[i + 7]) & MASK
            a, b, c, d, e, f, g, h = _mix(a, b, c, d, e, f, g, h)
            m[i], m[i + 1], m[i + 2], m[i + 3] = a, b, c, d
            m[i + 4], m[i + 5], m[i + 6], m[i + 7] = e, f, g, h
        self._isaac64()

    def _isaac64(self) -> None:
        self.cc = (self.cc + 1) & MASK
        self.bb = (self.bb + self.cc) & MASK
        aa = self.aa
        m = self.mm
        s = self.seed
        for i in range(256):
            r = i & 3
            if r == 0:
                aa = (~(aa ^ ((aa << 21) & MASK))) & MASK
            elif r == 1:
                aa ^= aa >> 5
            elif r == 2:
                aa ^= (aa << 12) & MASK
            else:
                aa ^= aa >> 33
            aa = (aa + m[(i + 128) & 255]) & MASK
            x = m[i]
            y = (m[(x >> 3) & 255] + aa + self.bb) & MASK
            m[i] = y
            self.bb = (m[(y >> 11) & 255] + x) & MASK
            s[i] = self.bb
        self.aa = aa

    def rand(self) -> int:
        result = self.seed[self.rand_cnt]
        if self.rand_cnt == 0:
            self._isaac64()
            self.rand_cnt = 255
        else:
            self.rand_cnt -= 1
        return result

    def keystream(self, size: int = KEYSTREAM_SIZE) -> bytes:
        out = bytearray(size)
        pos = 0
        while pos < size:
            v = self.rand().to_bytes(8, "big")
            n = min(8, size - pos)
            out[pos:pos + n] = v[:n]
            pos += n
        return bytes(out)


def decrypt(data: bytes, decode_key: int, size: int = KEYSTREAM_SIZE) -> bytes:
    """解密视频号视频：仅 XOR 前 size 字节，其余原样保留。"""
    ks = WxIsaac64(int(decode_key)).keystream(min(size, len(data)))
    out = bytearray(data)
    for i in range(len(ks)):
        out[i] ^= ks[i]
    return bytes(out)
