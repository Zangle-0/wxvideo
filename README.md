# wxvideo · 微信视频号下载器

> by **zangle**

把微信视频号（视频号 / WeChat Channels）的视频导出成可播放的 MP4。

- **纯本地运行**：不收集、不上传任何视频、链接或数据。
- **零第三方二进制**：手写 **纯 Python** 的 WxIsaac64 密钥流，**不依赖 wasm、不依赖 Node、不内置腾讯的解密模块**（也因此没有"内置资产"带来的法律风险）。
- **内嵌 mitmproxy**：抓包在本进程内完成，不是外挂 `mitmdump.exe`，没有孤儿进程和黑框。
- **代理安全守护**：退出/崩溃都会自动还原系统代理，界面还有「一键恢复网络」。

> 仅支持 **Windows 10/11 (x64)**。仅供个人学习与研究，详见文末[免责声明](#隐私安全与免责声明)。

---

## 下载使用

1. 到 **Releases** 页面下载 `wxvideo-<版本>-win64.zip`，解压到任意目录。
2. 运行 `wxvideo.exe`。
3. 首次使用：**设置 → 安装证书**（装到「当前用户 → 受信任的根」，会弹一次系统确认，无需管理员）。
4. 点 **开始监听**。
5. 在微信里载入视频号（把视频号窗口关掉再打开，或点开分享链接），**播放**想下载的视频 —— 它会出现在列表里。
6. 选清晰度（默认「最佳画质」，另有「省流」），点 **下载**。完成后界面会给出保存路径。
7. 用完点 **停止监听** 或直接关窗口（系统代理会自动还原）。

### 系统要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（64 位） |
| 运行时 | WebView2（Win10/11 通常自带；界面打不开时安装 *Microsoft Edge WebView2 Runtime*） |
| 其他 | 微信 PC 客户端已登录，且能打开视频号 |

### 关于 SmartScreen / 杀软提示

本程序的正当行为包含"**设置系统代理** + **安装根证书（中间人解密）**"，这类行为容易被安全软件误判；发布包**未做代码签名**，Windows SmartScreen 可能提示"未知发布者"。可以：

- 核对随包发布的 **SHA256**（`wxvideo-<版本>-win64.zip.sha256`）；
- 或直接从源码构建（见[开发](#开发)）——本项目开源，代码可审计。

---

## 工作原理

```
微信 PC 客户端 ──HTTPS──▶ mitmproxy（内嵌 · 127.0.0.1:8080）──▶ 腾讯服务器
     ▲ （系统代理指向它）              │
     │                                 │ 改写视频号页面 HTML，注入钩子脚本
     │                                 ▼
  载入/播放视频号 ──bridge(xweb.worker / WeixinJSBridge)──▶ 钩子脚本
                                                             │ POST 元数据
                                                             ▼
                                                    本地 API（127.0.0.1:随机端口）
                                                             │
                                        SQLite 入库 ──WebSocket──▶ 界面列表
                                                │
                              下载加密视频 ──▶ 前 128KB 与 ISAAC64 密钥流 XOR ──▶ MP4
```

1. **抓包**：启动时把系统代理指向本程序内嵌的 mitmproxy。
2. **注入**：微信加载视频号页面时，把返回的 HTML 改写，注入一小段脚本，钩住微信原生的 `xweb.worker` / `WeixinJSBridge`，把视频元数据（`decode_key`、下载地址、标题、作者、清晰度档位…）回传到本地 API。
3. **下载 + 解密**：视频号**只加密文件前 128KB（131072 字节）**。用 `decode_key` 作种子生成等长密钥流，与密文前 128KB 逐字节 XOR 即还原成 MP4。

> 关键约束：`decode_key` 只有**微信客户端渲染视频号页面时**才会产生，所以必须有一次"在监听开启状态下打开视频号"的动作。

---

## 截图

> 待补：`docs/screenshot-listen.png`、`docs/screenshot-library.png`、`docs/screenshot-settings.png`

---

## 已知限制（诚实说明）

- **仅 Windows**（代理守护、证书管理目前是 Windows 实现）。
- **需要"打开一次"**：普通 HTTP 拿不到 `decode_key`，必须让微信在监听状态下载入一次页面。
- **依赖微信客户端现状**：微信改版可能导致注入点/接口变化，届时需要适配（会跟进，但无法保证即时）。
- **未做代码签名**：SmartScreen/杀软可能提示（见上）。
- 抓包期间系统代理会临时指向本程序；正常退出会还原。

### 路线图

- [ ] 剪贴板监听（复制链接即自动定位目标）
- [ ] 自动下载 + 完成后「播放 / 打开目录」+ 系统通知
- [ ] 首次启动向导
- [ ] 托盘与关闭到托盘
- [ ] 库搜索 / 筛选

---

## 常见问题

**抓不到视频？**
在微信里**重新加载页面**：把「视频号」窗口关掉再打开，或点开分享链接；不要只是播放旧页面上的缓存。

**下载后不能播放？**
`decode_key` 与下载地址是**每次抓取才有效**的。请在本次监听中重新播放该视频，再点下载。

**列表里为什么有一堆我没点开的视频？**
视频号会一次性把整屏视频的元数据都拉下来（还会预取相邻视频）。默认按"最近播放 / 链接目标"排序并置顶，你点对的那条一眼可见；切到「全部历史」可看全部。

**能不能只给链接、完全不用打开微信？**
不能，且刻意不做。`decode_key` 由微信客户端渲染页面时经原生 bridge 产生，普通 HTTP 拿不到；存在一条"免打开"的旁路（借第三方接口解析分享链接），但它依赖非官方、随时可能失效的接口，会引入更大不稳定性，因此本项目不依赖它。现有做法：粘贴链接 → 在微信打开一次 → 程序自动识别为「链接目标」。

**会不会上传我的数据？**
不会。所有抓取/解密都在本机完成，数据目录在 `%LOCALAPPDATA%\wxvideo`。停止监听或退出即还原系统代理。

**怎么彻底卸载？**
删掉程序目录；在「设置」里卸载根证书（或 `certmgr.msc` → 受信任的根证书颁发机构 → 删除 `mitmproxy` 证书）；数据目录 `%LOCALAPPDATA%\wxvideo` 可一并删除。

---

## 开发

```powershell
# 1) 后端依赖
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt

# 2) 前端
cd web; npm install; npm run build; cd ..

# 3) 自检 / 单元测试 / 解密单文件
python run.py doctor
python tests\test_isaac64.py
python run.py decrypt <加密文件> <decode_key> [输出.mp4]

# 4) 图形界面
python run.py gui
```

### 目录结构

```
core/wxvideo_core/    Python 核心
  isaac64.py          纯 Python WxIsaac64（密钥流 + 解密）
  proxy.py            内嵌 mitmproxy + 页面注入
  netguard.py         系统代理安全守护（记录 / 还原 / 自愈）
  certs.py            根证书生成 / 安装 / 卸载（无黑框、带缓存）
  media.py            桥接数据解析
  download.py         流式下载 + 解密
  store.py            SQLite（视频 / 抓取 / 下载 / 设置 / 事件）
  runtime.py          编排：代理 + 本地 API + WebSocket
  cli.py / gui.py     命令行 / pywebview 界面
web/                  Vite + Vue3 + TS 前端
packaging/            PyInstaller 入口与 spec
scripts/build.ps1     本地一键打包（出 zip + SHA256）
tests/                单元测试与冒烟测试
run.py                开发入口
```

### 打包

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

或推送 `v*` tag，由 GitHub Actions（`.github/workflows/build.yml`）自动构建并发布 Release（附 SHA256）。

---

## 隐私、安全与免责声明

- **隐私**：不收集、不上传任何内容；不写开机自启；除本程序自身外不注入其它进程。
- **安全**：根证书只用于解密**本机**经本程序代理的流量，可随时卸载；系统代理在退出/崩溃后会自动还原。
- **免责声明**：本软件**仅供个人学习与研究**。下载他人内容可能涉及版权，请勿传播、二次发布或用于商业用途；使用本软件产生的任何版权与合规责任由使用者自行承担。请遵守相关平台的服务条款与当地法律。

## License

[MIT](LICENSE)

## 致谢

- ISAAC64 解密算法：Hanson/[WechatSphDecrypt](https://github.com/Hanson/WechatSphDecrypt)、[wx_channels_download](https://github.com/ltaoo/wx_channels_download)。
- 加密机制逆向分析：看雪《微信视频号视频加密逆向》（Aynakeya）等公开资料。
