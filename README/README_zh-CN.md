# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** 是一套跨平台的 Python GUI 自动化框架。它能驱动鼠标与键盘、在画面上找到目标
（模板匹配、OCR、操作系统无障碍树，或视觉模型）、录制与回放操作流程，并以 JSON 动作文件执行——
支持 Windows、macOS、Linux（X11 与 Wayland）、BSD、Android 与 iOS。

每项能力都以三种形式提供：**Python API**、可在 JSON 文件／CLI／服务器使用的 **`AC_*` 动作命令**，
以及 **GUI 标签页**。没有任何功能只存在于 GUI。

**[English](../README.md)** · **[繁體中文](README_zh-TW.md)**

---

## 为什么选择 AutoControl

- **一套 API，七个平台。** `wrapper/platform_wrapper.py` 在导入时挑选后端；同一份脚本在
  Windows、macOS、X11 与 Wayland 上都不需要改写。
- **不写 Python 也能脚本化。** 819 个 `AC_*` 命令覆盖全部功能，因此一个 JSON 文件能做到库
  能做的任何事——包含循环、分支、try/catch、宏与变量。
- **默认无头运行。** `import je_auto_control` 绝不会加载 Qt。GUI 是可选包，包在同一个无头内核之外。
- **四种定位方式。** 模板匹配、OCR、无障碍树、视觉语言模型——可通过锚点定位器与自愈回退串接组合。
- **依赖基线轻量。** REST 服务器、JSON Schema 校验、JWT、TOTP、WebSocket 帧、ACME 客户端、
  USB/IP 协议与 Prometheus 指标全部以标准库实现；较重的依赖都是可选项。

---

## 安装

```bash
pip install je_auto_control            # 内核
pip install je_auto_control[gui]       # 加上 PySide6 桌面应用
```

按需安装的可选组件：

| Extra | 启用的功能 |
|---|---|
| `gui` | PySide6 桌面应用（50 个标签页） |
| `webrtc` | WebRTC 远程桌面、USB 直通（`aiortc`、`av`） |
| `signaling` | 独立的信令／rendezvous 服务器（`fastapi`、`uvicorn`） |
| `discovery` | mDNS / Zeroconf 局域网主机发现 |
| `pdf` / `office` | PDF 与 Excel／Word／PowerPoint 读取 |
| `fuzzy` / `locale` | `rapidfuzz` 模糊匹配、`babel` 区域解析 |
| `s3` / `audio` | S3 制品存储、系统音量控制 |

**Windows arm64** 的 `find_image*`、BGR `screenshot()` 与固定画面自愈使用
NumPy／Pillow 后端，基本安装包含 NumPy 2.4.6。高级 OpenCV 处理／视频与安全版本
cryptography 仍缺上游 wheel；密钥金库、动作签名／加密、ACME／TLS 与加密录影
仍不可用。共享后端的依赖错误属于框架异常家族。platform smoke job 已加入
原生 arm64 图像测试；本机替代后端测试会阻止 OpenCV 加载，并保留现有契约。

**系统需求：** Python ≥ 3.10（Windows arm64≥ 3.11，CPython 官方构建从那里开始）。
Linux 请先安装构建依赖：

```bash
sudo apt-get install cmake libssl-dev
```

OCR、VLM 与 LLM 后端（`pytesseract`、`easyocr`、`paddleocr`、`anthropic`、`openai`）
都是按需加载——只装你实际会用到的。

**日志文件：** 库写到 `~/.je_auto_control/logs/AutoControlGUI.log`，第一条记录时
才创建（只 import 不会写任何文件），同一个账户的所有进程共用（追加写入、每行带进程 ID，
超过 10 MB 就改名为 `.1`）。要写到别处就设置
`JE_AUTOCONTROL_LOG_FILE`，设为 `os.devnull` 则不写文件。

---

## 60 秒上手

**1. 作为 Python 库**

```python
import je_auto_control as ac

ac.set_mouse_position(500, 300)
ac.click_mouse("mouse_left")
ac.write("Hello World")
ac.hotkey(["ctrl_l", "s"])

x, y = ac.locate_image_center("save_button.png", detect_threshold=0.9)
ac.click_text("Submit")                       # OCR
ac.click_accessibility_element(name="OK")     # 无障碍树
ac.click_by_description("the green Submit button")   # 视觉模型
ac.screenshot("shot.png", screen_region=[0, 0, 800, 600])
```

**2. 作为 JSON 动作文件** — `flow.json`

```json
[
    ["AC_set_var", {"name": "user", "value": "alice"}],
    ["AC_locate_and_click", {"image": "login.png", "mouse_keycode": "mouse_left"}],
    ["AC_write", {"write_string": "${user}"}],
    ["AC_retry", {"max_attempts": 3, "body": [
        ["AC_wait_text", {"target": "Welcome", "timeout": 10}]
    ]}],
    ["AC_assert_text", {"text": "Welcome"}],
    ["AC_generate_html_report", {"html_name": "report"}]
]
```

```bash
je_auto_control run flow.json --var user=bob
je_auto_control run flow.json --dry-run     # 只列出步骤，不会真的动鼠标
```

**3. 作为桌面应用**

```bash
pip install je_auto_control[gui]
python -c "import je_auto_control; je_auto_control.start_autocontrol_gui()"
```

录制一段流程、在可视化 Script Builder 里编辑，然后存成 CLI 能直接执行的同一种 JSON 格式。
（`python -m je_auto_control` 是旧式的动作文件执行器——`-e`、`-d`、`-c`、`--execute_str`——不会打开 GUI。）

---

## 能力总览

每一行都能无头执行。“GUI 标签页”是同一功能在桌面应用中的位置；标签页的命令都放在窗口的
**Actions** 菜单里。

| 能力 | Python API | `AC_*` 命令 | GUI 标签页 |
|---|---|---|---|
| 鼠标 | `click_mouse`、`set_mouse_position`、`mouse_scroll` | `AC_click_mouse` | Auto Click |
| 键盘 | `write`、`hotkey`、`type_keyboard` | `AC_write`、`AC_hotkey` | Auto Click |
| 屏幕与像素 | `screenshot`、`screen_size`、`get_pixel` | `AC_screenshot` | Screenshot |
| 图像匹配 | `locate_image_center`、`locate_and_click` | `AC_locate_and_click` | Image Detect |
| OCR 文字 | `click_text`、`wait_for_text`、`read_text_in_region` | `AC_click_text`、`AC_wait_text` | OCR Reader |
| 无障碍树 | `find_accessibility_element`、`click_accessibility_element` | `AC_a11y_find`、`AC_a11y_click` | Accessibility |
| 视觉模型定位 | `locate_by_description`、`click_by_description` | `AC_vlm_locate`、`AC_vlm_click` | VLM |
| 锚点定位 | — | `AC_anchor_click`、`AC_anchor_locate` | — |
| 自愈定位器 | `self_heal_click`、`self_heal_locate` | `AC_self_heal_click` | Self-Healing |
| 自然语言规划 | `plan_actions`、`run_from_description` | `AC_llm_plan` | LLM Planner |
| Computer-use agent | `AgentLoop`、`run_agent` | `AC_run_agent` | Computer Use |
| 录制与回放 | `record`、`stop_record` | `AC_record`、`AC_stop_record` | Record |
| JSON 脚本 | `execute_action`、`execute_files` | 全部 819 个命令 | Script、Script Builder |
| 变量与流程控制 | `execute_action_with_vars` | `AC_set_var`、`AC_loop`、`AC_for_each`、`AC_try`、`AC_retry` | Variables |
| 数据驱动执行 | — | `AC_for_each_row`（CSV／JSON／SQLite／Excel） | Data Sources |
| 断言 | `assert_text`、`assert_image` | `AC_assert_text` 等 21 个 | Assertions |
| 测试套件 | `run_suite` | `AC_run_suite` | Test Suites |
| 调度（间隔 + cron） | `default_scheduler` | — | Scheduler |
| 全局热键 | `default_hotkey_daemon` | — | Hotkeys |
| 事件触发 | `default_trigger_engine` | `AC_email_trigger_add` | Triggers、Webhooks、Email |
| 窗口管理 *(Windows、macOS、X11)* | `list_windows`、`focus_window` | `AC_focus_window`、`AC_snap_window` | Window Manager |
| 剪贴板（文本 + 图片） | `get_clipboard`、`set_clipboard`、`get_clipboard_image`、`set_clipboard_image` | `AC_clipboard_get`、`AC_clipboard_set`、`AC_clipboard_get_image`、`AC_clipboard_set_image` | — |
| 远程桌面 | `RemoteDesktopHost`、`RemoteDesktopViewer` | `AC_start_remote_host`、`AC_remote_connect` | Remote Desktop |
| USB 枚举与直通 | `list_usb_devices`、`enable_usb_passthrough` | `AC_usb_*`（16 个命令） | USB Devices、USB Share |
| 密钥保险库 | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| 报表（HTML／JSON／XML） | `generate_html_report` | `AC_generate_html_report` | Report |
| 运行历史 | — | — | Run History |
| 指标与追踪 | `default_metric_registry`、`render_metrics_text` | — | — |
| 系统诊断 | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| 测试代码生成 | `generate_code` | — | — |

除了这张表，`utils/` 下还有 311 个无头包，覆盖断言、韧性、数据质量、i18n 审计、脱敏、
治理、可观测性等等。完整的逐模块地图在 **[architecture_explore.md](../architecture_explore.md)**。

---

## 命令行界面

```bash
je_auto_control run script.json [--var name=value] [--dry-run]
je_auto_control validate script.json          # 别名：lint
je_auto_control fmt script.json [--check]
je_auto_control list-commands [--filter mouse] [--json]
je_auto_control record out.json [--duration 5]
je_auto_control codegen script.json --target pytest -o test_flow.py
je_auto_control failure-bundle failure.zip --error "login timed out"
je_auto_control list-jobs
je_auto_control start-server --port 9938      # TCP socket 服务器
je_auto_control start-rest   --port 9939      # REST API
je_auto_control version
```

`--var name=value` 会尽量以 JSON 解析（`count=10` 会变成整数），否则视为字符串。
`run` 只要有任何动作失败就以 1 退出（仍会跑完整份脚本），CI 步骤会随之失败。旧版 `python -m je_auto_control -e file.json` 入口仍然可用。

---

## 服务器与集成

| 接口 | 启动方式 | 说明 |
|---|---|---|
| **MCP 服务器** | `je_auto_control_mcp`（stdio）或 `AC_start_mcp_http_server` | 741 个工具，供 Claude Desktop／Claude Code／自定义 tool loop 使用。除了以 `initialize` 握手的各版协议，也支持无状态的 MCP 2026-07-28。Bearer 认证、TLS、审计日志、限流、插件热重载、CI 假后端。 |
| **REST API** | `je_auto_control start-rest` | Bearer token、按 IP 限流与锁定、SQLite 审计 hook、`/metrics`、`/openapi.json`、`/docs` Swagger UI、`/dashboard`。 |
| **TCP socket 服务器** | `je_auto_control start-server` | 以换行分隔的 JSON 动作列表。默认绑定 `127.0.0.1`。 |
| **pytest 插件** | 安装后自动生效 | 轻量 `je_auto_control_pytest` 入口，提供 fixture 与 Gherkin 步骤。升级 editable 工作树后须重新安装；明确指定的旧插件路径仍兼容。 |
| **语言服务器** | `python -m autocontrol_lsp.server` | 为 `AC_*` 动作 JSON 提供补全与诊断，命令清单直接取自运行期的命令表。 |
| **远程桌面** | `RemoteDesktopHost` 或 GUI | TCP、WebSocket 或 WebRTC；TOTP、信任列表、TURN 配置、文件／剪贴板／音频同步。 |

除非明确指定，旧版 `python -m je_auto_control -e/-d/--execute_str` 与 `je_auto_control run`
在动作失败时返回退出码 1，成功时为 0；目录执行累积所有文件的失败，stderr 报告失败数。

公开动作调用会隔离变量。需要跨调用共用时，使用
`with je_auto_control.execution_scope({"name": "value"}) as scope:`。
嵌套动作共用本次作用域，并行分支与 DAG 节点深复制变量；REST／MCP 请求各自隔离。
明确持有的 `Executor` 在公开作用域外保留自己的状态。

USB 直通以请求 ID 配对回复、分片数据与错误，迟到回复不会完成重试。
旧版或尚未确认能力的主机超时后，须重连并建立新 client；原 handle 的 `closed` 为真。
新版主机返回 ID，保留原有帧头与旧端点兼容性。

所有服务器都绑定在 `127.0.0.1`。

### 远程桌面的线路协议

把主机开放出去之前值得先了解，而且这一段在其他文档里都没有写。默认传输是**裸
TCP 上的长度前缀分帧**（不需要额外依赖），连接一开始就是 **HMAC-SHA256 的
challenge／response 握手**：认证不通过的观看端在拿到任何一帧之前就会被断开。
JPEG 帧按配置的 FPS 与质量编码，再通过一个共享的**最新帧槽**发给已认证的观看
端——所以慢的观看端是**丢帧**，不会把其他人一起卡住。观看端发来的输入是 JSON，
会先比对**动作允许列表**才交给既有的输入包装层执行，观看端无法自己发明新的操作。

```python
# 让别人连进来——启动一个主机，把 token 与 port 给对方
from je_auto_control import RemoteDesktopHost
host = RemoteDesktopHost(token="hunter2", bind="127.0.0.1",
                         port=0, fps=10, quality=70)
host.start()
print("listening on", host.port, "viewers:", host.connected_clients)
```

```python
# 控制另一台机器——连上去并发送输入
from je_auto_control import RemoteDesktopViewer
viewer = RemoteDesktopViewer(host="10.0.0.5", port=51234, token="hunter2",
                             on_frame=lambda jpeg: ...)
viewer.connect()
viewer.send_input({"action": "mouse_move", "x": 100, "y": 200})
viewer.disconnect()
```

也可以用 IP 允许列表（CIDR 网段或具体地址）限制谁能连进来，列表外的对端在握手
阶段就会被拒绝：

```python
RemoteDesktopHost(token="tok", ip_allowlist=["10.0.0.0/8", "192.168.1.100"])
```

---

## 平台支持

| 平台 | 后端 | 输入 | 屏幕捕获 | 录制 | 窗口管理 |
|---|---|:---:|:---:|:---:|:---:|
| Windows 10 / 11 | Win32 ctypes（可选 Interception 驱动） | ✅ | ✅ | ✅ | ✅ |
| macOS 10.15+ | pyobjc / Quartz | ✅ | ✅ | ✅¹ | ✅ |
| Linux X11 | python-Xlib（可选 `uinput`） | ✅ | ✅ | ✅ | ✅ |
| Linux Wayland | 经桌面 portal 的 libei，或 ydotool／wtype ＋ 截图工具 | ✅ | ✅ | ❌ | ❌ |
| FreeBSD／OpenBSD／NetBSD | python-Xlib，与 Linux 同一套 X11 后端 | ✅² | ⚠️² | ✅² | ✅² |
| Android | adb + uiautomator2 | ✅ | ✅ | — | — |
| iOS | WebDriverAgent / facebook-wda | ✅ | ✅ | — | — |

Beta `je_auto_control.api.mobile` 新增冻结的 `DeviceContext` identity，以及延迟创建的
`open_device(context)` session，提供 `bind()`、`capabilities`、`cancel()` 与可重复 `close()`。
矩阵 worker 各有独立 owner，未指定 target 的 mobile 命令也使用它；重复配置的 target
及外来 client override 会被拒绝。binding 外的 helper 保留兼容默认值。原生请求超时
各自受 owner 限制；取消会拒绝迟到结果，且只回收该 client 启动的 Android helper。
`connected` 仅代表逻辑生命周期。`probe_device_contexts`、`AC_probe_mobile_devices` 与 MCP
`ac_probe_mobile_devices` 不连接或输入，只检查依赖；远程查询需 host admin。
Device Matrix 在 Actions 提供查询，矩阵改在后台执行；Script Builder 共用命令。
见[移动设备指南](../docs/source/Zh/doc/mobile/mobile_doc.rst)及
[不操作硬件的示例](../examples/mobile_contexts.py)。设备可达性、授权、SDK bootstrap
整体截止时间与恢复仍列验收。

`DeviceSession` 另提供 `capture()`、`perform(Gesture)` 与 `type_text()`。
`DeviceFrame` 保存不可变 PNG、原生 viewport／方向及 `pixel_to_point()`；`rotated()`
保留换算。UIKit point 不等于 Retina 截图 pixel，旧 iOS 数值输入保持兼容。
Gesture 附上 `frame=frame` 时，输入前再检查 owner／geometry。
捕获时方向改变或宽高比不符会拒绝，避免猜测旋转。Android Unicode 经 SDK
IME／剪贴板路径；`AdbClient.text`／`AC_android_text` 在输入前拒绝非 ASCII。
SDK 可能设置输入法／剪贴板，原生恢复仍列验收。frame 的 `ocr()`、`locate(strategy)`
共用已有 bytes；binding 内的 `self_heal_locate`／`self_heal_click` 使用同一设备画面
及原生 touch，不退回桌面。mobile 全画面搜索拒绝桌面 `screen_region` 与非左键。
`mobile_capture`、`mobile_gesture`、`mobile_type_text` 对应 `AC_mobile_*`、MCP
`ac_mobile_*` 与 Builder schema，可在 Device Matrix Actions 执行。需提供 device
对象或使用矩阵 owner；远程操作需 host admin。文字在 action／journal 参数中遮罩，
响应不复述。WDA pinch 需支持 `/actions`，失败属于框架异常。
[画面换算示例](../examples/mobile_frame_mapping.py) 不会输入。

图像匹配与 `screenshot()` 优先使用 OpenCV；缺少时使用 NumPy／Pillow 后端。
Windows arm64 的 Python 3.11+ 会安装 NumPy 2.4.6。归一化灰度匹配、BGR 截图数组、
图像文件解码／编码、匹配预览及固定画面自愈沿用现有 Python／AC／GUI／MCP 入口。
替代后端接受 uint8／float32 数组与 8-bit 图像文件；画面最多 16,777,216 像素，
每个分块 FFT 最多 4,194,304 格，超出预算或不支持的操作会抛出框架类型错误。
高级 OpenCV 处理／视频与加密／签名仍需其原生依赖。

¹ macOS 的录制走 Quartz event tap，需要**辅助功能**权限
（系统设置 → 隐私与安全性 → 辅助功能）。没有授权时会直接抛出并指名
缺的是哪个权限，而不是安静地录到一个空的 session。

² BSD 直接跑同一套 X11 后端——同一个 X server、同一个 `python-Xlib`，而输入、
录制与窗口管理就只依赖这一个包。`freebsd` CI job 在真的 FreeBSD 14 上驱动真的
输入，再从 X server 读回来；OpenBSD 与 NetBSD 走同一条代码路径，只是没有 CI
runner。唯一的例外是屏幕截取，卡住的是打包而不是平台：它走 Pillow／mss 与
OpenCV 或 NumPy 转换，而 `opencv-python`、`pillow`、`cryptography` 都没有发 FreeBSD wheel。
从 ports 构建之后，截取、图像匹配、OCR 与动作加密也都能用——
`import je_auto_control` 本身已经不需要它们任何一个。

Wayland 输入默认使用 libei；CLI 输入需明确设置
`JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli`，并安装 **ydotool 1.0 以上**。AutoControl 送的每一个参数都是那一版才有的；0.1.x
（Debian bookworm 与目前所有 Ubuntu 仍以这个名字提供，Debian trixie 则根本没有）
对同一批参数返回 0 却不送出任何事件。AutoControl 会检测并直接拒绝，
而不是为根本没送出的输入回报成功。Arch、Fedora 与 Debian unstable 提供的是 1.0。

`probe_capabilities()`（Beta `je_auto_control.api.capabilities`）、
`AC_probe_capabilities` 与 MCP `ac_probe_capabilities` 分别报告输入／截图状态（`available`、`needs_permission`、
`needs_dependency`、`unsupported`），不请求授权、不发送输入、不截图，也不加载原生库。
XWayland 明确限于 X11 窗口；发现工具不代表已验证合成器支持。原生授权取消、失败或撤销时
停止输入，不自动选择 CLI。Wayland 诊断的 Actions 菜单可停止原生控制或允许新的授权尝试；
下一次明确输入请求才显示授权。当前 liboeffis 绑定不支持 restore token，也不保存 token。

默认 libei session 在专用 helper 子进程执行。私有 JSON IPC 每条消息上限
64 KiB，每批最多 128 个事件；输入请求时限 3 秒，启动与授权总时限 38 秒。
超时、取消或 helper 死亡会终止连接并要求明确重新授权，不重发结果不明的输入。
正常关闭会在同一份授权下释放已按住的键与按钮；crash 后的撤销设备清理由合成器负责。
诊断的停止／重试操作沿用这份生命周期。`LibeiBackend` 保留为原生验证使用的
低层进程内绑定，直接调用者须负责其进程生命周期。

GUI 与 `AC_diagnose` 默认使用被动检查；`AC_diagnose include_active=true` 才执行截图／光标检查。
Python 为兼容保留默认的主动诊断，被动模式使用 `run_diagnostics(include_active=False)`。
这些本机功能不需要付费 API 或 API key。


这条退路要能**准确定位**，还有一个前提:合成器的指针加速度必须是关的。
`ydotool mousemove --absolute` 并不发任何绝对事件——它先把光标推到合成器夹取的
那个角落，再发相对位移，所以这段位移会被合成器加速。对真的 wlroots session 量到的是:
libinput 的默认 profile 让光标走的距离正好是请求的两倍。ydotool 自己的 `--help`
也是这样写的；AutoControl 每个进程会记一次警告，而不是安静地把点击放到错的地方。
请对 ydotoold 的设备关掉加速度（sway:`input type:pointer accel_profile flat`
加上 `pointer_accel 0`），或者装上 `liboeffis`，改走协议层本来就是绝对坐标的 libei。

倍率是合成器自己的设置，客户端读不回来，所以只有你知道它关了没有：
`JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat` 表示已经关掉，移动就不再出声；
`=strict` 则宁可拒绝这次移动，也不让点击落在别的地方；不设置就维持
“警告一次后照样移动”的默认。

Wayland 的屏幕截取需要合成器对应的工具，因为没有单一工具能覆盖全部：wlroots 系
（sway、Hyprland、river）用 `grim`，GNOME 用 `gnome-screenshot`，KDE 用 `spectacle`。
装好其中一个之后，所有截取路径——截图、图像与锚点定位、OCR、屏幕录制、远程桌面——都会
经由它。三个都没装也还有 `gdbus`：最后会尝试 `xdg-desktop-portal`，只是第一次可能会弹
同意对话框。再不行，截取会带着安装提示明确失败，而不是返回空白的 XWayland root；
`je_auto_control.api.run_diagnostics()`（以及 GUI 的 Diagnostics 标签页）的 `screen_capture`
检查会报告当前使用的是哪一层。

有一件只在 Wayland 出现、需要事先规划的事：**截取回来的图里可能有鼠标光标。**
这里没有任何一条截取请求光标，但只要 backend 没有光标平面（包含任何以
`WLR_NO_HARDWARE_CURSORS=1` 运行的 session），wlroots 就会画**软件光标**并把它
合成进输出缓冲区，而截取交回来的正是那一份。Windows 与 X11 都不含光标，所以
“定位器、模板匹配或 OCR 在目标中间看到一个光标形状的洞”只会在这里发生。
Wayland 不让客户端读光标位置，所以没有东西可以可靠地遮或避开：请在截取之前
把指针移离要拍的区域。`screen_capture` 检查会以 `cursor_may_be_captured` 报告这件事。

如果以上都不适用你的环境，可以直接指定自己的命令——它优先于所有检测，`{output}` 会被
换成临时 PNG 路径：

```bash
export JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mycapture --png {output}"
```

Executor 动作日志不需要全局输入 hook。实验中的 Wayland `PhysicalRecorder` 底层
使用已有读取权限，读取明确选定的实体 `/dev/input/event*` 节点，排除内核 virtual／uinput
设备；返回原始设备事件，不转为桌面坐标或回放动作，也不修改 ACL。
`StopShortcutSession` 会明确请求 portal 停止快捷键、显示实际绑定并关闭自己的授权；
拒绝后须先 close 再 start 才重试。Beta `je_auto_control.api.wayland_input` 与旧门面提供上述底层及五个脚本操作：
`start_physical_recording(devices)`、`stop_physical_recording()`、
`start_wayland_stop_shortcut(preferred_trigger='F7')`、`stop_wayland_stop_shortcut()`、
`wayland_input_status()`。各有 `AC_*` 命令、小写 MCP 工具与 Script Builder schema。
动作日志遮罩原始停止结果；远程 RBAC 的五项操作均要求主机管理权限。
诊断页提供明确 Actions、JSON 设备路径输入、希望使用的快捷键、实际绑定／状态与原始结果；
每个面板与脚本默认资源独立持有。停止绑定会停止原生输入控制并设置持有者的合作取消
`stop_event`，不会中断任意 Python 工作。原生桌面验收仍列于 D3／H3。停止与明确重试可取消待授权的原生连接，不会等待其 cache 锁；取消后的 grant 不能再被发布。
旧 Wayland 全局录制 hook 仍不可用。窗口管理支持
Windows、macOS（pyobjc）与 X11（含 XWayland）；纯 Wayland 会话的协议不让客户端看到其他程序的窗口，
所以 `list_windows()` 返回空列表，其余窗口操作一律抛出带原因的 `AutoControlUnsupportedOperationException`。对于会忽略合成输入的应用，
可选用驱动层后端（`JE_AUTOCONTROL_WIN32_BACKEND=interception`、
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`、ViGEm 虚拟手柄）；驱动未安装时会自动回退到原有行为。

---

## 文档与示例

| 资源 | 内容 |
|---|---|
| [`examples/`](../examples/) | 29 个自包含脚本：截图点击、OCR、调度器、远程桌面、agent loop、可观测性、录制、变量、热键、触发器、报表、MCP、REST、密钥、插件、computer use、Wayland、跨主机 DAG、chat-ops、pytest/BDD、锚点定位。 |
| [Read the Docs](https://autocontrol.readthedocs.io/en/latest/) | 完整 API 参考，含英文与中文。 |
| [architecture_explore.md](../architecture_explore.md) | 逐层记录每个模块的职责。 |
| [docs/CAPABILITY_MATRIX.md](../docs/CAPABILITY_MATRIX.md) | 能力 × 平台对照矩阵。 |
| [docs/API_LIFECYCLE.md](../docs/API_LIFECYCLE.md) | 稳定 API 与弃用策略。 |
| [docs/updates/](../docs/updates/README.md) | 更新记录：各版本说明与完成的工作，每月一个文件（原 `WHATS_NEW.md`）。 |
| [CHANGELOG.md](../CHANGELOG.md) | 兼容性变更记录。 |
| [SECURITY.md](../SECURITY.md) | 安全策略与报告方式。 |

---

## 开发

```bash
git clone https://github.com/Integration-Automation/AutoControlGUI.git
cd AutoControl
pip install -r dev_requirements.txt
uv sync                 # 或：以已提交的 uv.lock 做可重现安装
```

```bash
python -m pytest test/unit_test/headless      # 无头单元测试
python -m pytest test/integrated_test/        # 跨模块流程测试

ruff check je_auto_control/
pylint je_auto_control/
bandit -c pyproject.toml -r je_auto_control/
```

欢迎贡献——请见 [CONTRIBUTING.md](../CONTRIBUTING.md) 与
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)。CI 会强制两条规则：`import je_auto_control`
绝不能加载 PySide6；每个功能都必须同时具备无头 API 与 GUI 界面。

Linux／macOS Python 3.10 quality job 通过 gdb／lldb 保存 `native-diagnostics`
artifact，包含原生堆栈、包版本及测试退出码。原有 coverage 命令及断言继续执行；
收集诊断不代表已定位 USB ACL 的间歇崩溃原因。
LLDB 跳过启动器的 exec 暂停；其他非致命停止会视为诊断失败，不捏造崩溃退出码。
两个 debugger 都将 SIGINT 传给 Python，让紧急停止断言正常执行。
Quality 测试安装 WebRTC／signaling extras 与 HTTP 测试 client。
GUI 翻译表保留子组件 wrapper，对自身组件使用 weak proxy，避免自身循环引用
把 GUI 销毁延后到工作线程的 GC。

共享 D-Bus 取消会移除连接并唤醒进行中的 I/O；最后一个操作退出时才关闭 descriptor。
读取每 100 ms 检查取消，保留原请求时限，拒绝取消后的完成结果；旧 descriptor
回收前不能重连。


macOS Quartz／AppKit 与录制 tap 仅在原生操作时加载，导入及纯 CLI 文件错误
不初始化这些框架。显式 `grab_logical(metrics=...)` 在所有平台采用虚拟画面几何；
macOS 默认捕获仍逐屏幕转成 Retina points。EI helper 取消也会保留 socket 至
transaction 退出，以短轮询保留总时限，并拒绝取消后的完成结果。

Docker CI 可手动选择 `d3-native`，执行 sway、EIS、portal、seat 与 uinput
检查。seat／uinput 镜像用已安装的 wheel 验证真实 ydotool 内核设备会在打开前
被排除，没有录回事件或遗留描述符；原生失败日志保存 14 天。执行命令与证据范围见
[Wayland 验收](../docs/WAYLAND_ACCEPTANCE.md)。

手动运行 `quality.yml` 可选 `verification_scope=native-shortcut`，仅跑 installed-wheel／
私有 bus 检查；默认会运行全部 quality jobs。

portal owner 消失或替换会撤销待授权及有效的快捷键 grant；有效 grant 撤销时
通知该 owner 的停止 callback。原生传输验证使用独立 GDBus、私有 bus 与 installed wheel，
不代表 GNOME／KDE 真人授权或实体键态恢复已验收。

---

## 许可

[MIT License](../LICENSE) © JE-Chen。
内含与可选第三方组件的许可请见 [Third_Party_License.md](../Third_Party_License.md)。

- **主页**：https://github.com/Integration-Automation/AutoControlGUI
- **PyPI**：https://pypi.org/project/je_auto_control/
- **文档**：https://autocontrol.readthedocs.io/en/latest/

动作文件使用 Ed25519 第 2 版 JSON 签名侧文件。使用
`je_auto_control signing-keygen --private-key private.pem --public-key public.pem`
创建密钥，`je_auto_control sign flow.json --private-key private.pem` 签署，
`je_auto_control verify flow.json --public-key public.pem` 验证。执行端只部署公钥，
设置 `JE_AUTOCONTROL_SIGNING_PUBLIC_KEY` 与 `JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS=1`；
私钥保留在离线签署端。验证不会创建密钥；旧 HMAC 必须明确开启迁移选项。
完整部署和迁移示例见中英文 Sphinx 功能文档。

MCP 使用 schema 语义标记真正的文件字段，JSONPath、包名称和普通文本保留原义。
`JE_AUTOCONTROL_MCP_ROOTS` 指定允许根目录，以 OS 路径分隔符分开
（Windows 用 `;`，Unix 用 `:`）。各连接的 `roots/list` 与部署设置取交集；
空列表拒绝文件参数，未设置时在收到 client roots 前保留原有文件访问。
这不会自动开启只读模式。MCP 默认拒绝 `env://`，使用
`JE_AUTOCONTROL_MCP_ALLOWED_ENV=PUBLIC_SETTING,BUILD_ID` 明确允许名称；
`file://` 使用同一根目录策略。本机 Python 解析保留原行为，可明确传入
`policy=je_auto_control.PathPolicy(...)`。

TCP／WebSocket viewer 默认收文件到 `~/Downloads/AutoControl`，本机可用
`JE_AUTOCONTROL_DOWNLOAD_DIR` 指定目录。Host 必须传入 `reports/result.txt` 等相对
目的地；绝对路径、磁盘／UNC、目录穿越和 symlink 越界会被拒绝。
可用 `FileReceiver(base_dir=Path(...))` 选择其他受限目录；host 收文件保留原行为。

屏幕区域使用全局输入坐标，包含副屏幕的负坐标。新 Windows 进程在 GUI 初始化前
优先启用 per-monitor DPI v2；缩放副屏幕上以旧系统 DPI 策略录制的坐标与模板
需要重新录制。嵌入的主程序保留已设置的 DPI 策略。macOS 逐屏幕缩成 point
后拼接，主屏幕与区域截图也使用 point，并支持较旧的 Pillow。
Set-of-Marks 图例保留全局坐标，结果提供捕获的 `origin`。

Anthropic Agent 历史在三张截图上限内只追加；超过时以目标、已完成动作数、
最近五十个动作及结果、最新截图建立新对话。已发送的消息与签署 thinking 区块
保持原样，不移入新对话。常规工具、beta computer-use 与 GA toolset 都适用。
`AC_run_agent` 沿用现有默认工具导出。付费 API 验证需配置 key，待办见 `Progress.md`。


REST／MCP 个人身份采用 opt-in：以 `UserStore(Path("users.json"))` 创建用户，
角色可选 `viewer`、`operator`、`admin`，启动服务器或 GUI 前将
`JE_AUTOCONTROL_USERS` 设为该文件。viewer 可观察画面；operator 可操作输入与
顺序动作脚本；admin 可额外管理用户、主机、文件、签名、审计与后台工作。
工具搜索与调用使用相同权限，嵌套 executor 命令也检查。
未设置变量时保留共享 token；已设置但用户文件为空或不可读时拒绝登录。
HTTP MCP 会话仅属于已验证的用户，审计记录包含 `user_id`。

Admin Console 的 Actions 菜单提供刷新、新增、移除、角色与 token 轮替，
与本机服务器共用同一 UserStore。门面公开 `rbac_*` 与 `UserStore`；
JSON／Script Builder 提供 `AC_user_add`、`AC_user_list`、`AC_user_remove`、
`AC_user_set_role`、`AC_user_rotate_token`，MCP 使用对应小写名称。
命令 token 可由 `${secrets.USER_TOKEN}` 提供，结果仅含用户资料。
GUI 生成的 token 仅显示一次供保存。


加密依赖下限为 `cryptography>=50.0.0`（lock：50.0.2）。Windows arm64 保留
optional markers，上游仍无符合安全下限的 wheel；Intel Mac 需源码编译。
详见[安装矩阵](../docs/CAPABILITY_MATRIX.md)。缺少依赖时，相关能力抛出
门面公开的 `CryptoDependencyError`；`CryptoUnavailableError` 兼容 RuntimeError，
`CryptoImportError` 兼容 ImportError。错误附安装指引，非加密操作与 Qt-free 导入可继续使用。

## 窗口生命周期与布局快照

`focus_window` 确认实际前台窗口，焦点被拒时抛出
`AutoControlActionException`。`wait_for_window` 每次等待不超过剩余超时，也支持无限 poll 值。
Windows 枚举跳过 DWM 隐藏和零面积窗口；投递文本只发送一次字符消息，控制键发送含扫描码和
释放标志的成对按键消息，并接受 `enter`、`esc` 别名。

`capture_window` 读取可见边界，不移动或还原窗口。新的 Windows `save_window_layout`
快照包含原生位置和显示状态，`restore_window_layout` 还原时不会因边框而偏移，并保留最大化／
最小化状态。旧版只有几何数据的 JSON 仍可读取；重新保存快照才能保留原生位置。
注入的 geometry／mover 仍沿用几何契约。贴齐／网格／层叠排列使用含原点偏移的主屏幕工作区，
避开任务栏。macOS 按窗口 ID 还原时查询离开屏幕的窗口，仍须取得 Accessibility 授权。

## 键盘正确性与秘密输入

`write("Hi\r\nthere")` 保留大小写，CRLF 只按一次 Enter。Windows 的字面文本
优先使用 Unicode 注入；明确指定 `is_shift=True` 时，Windows／X11 与 macOS 都会
按住及释放 Shift。Windows 快捷键接受 `plus`、`minus`、`comma`、`period`、`slash`
等 OEM 名称。`type_unicode_keys` 将换行／Tab／退格发送为控制键。布局表包含区域 OEM
键，Shift 半边无法翻译时返回 `None`。

秘密文本使用 `ac.write_secret(secret)` 或 `ac.write(text, secret=True)`。
两者返回 `None`，不留下输入日志或录制记录；后端失败信息改为通用的框架异常。
脚本使用 `["AC_write_secret", {"secret": "${secrets.LOGIN}"}]`；MCP 提供
`ac_write_secret(secret=...)`。Script Builder 隐藏秘密字段；请保存秘密引用，因为
动作文件仍会包含传入的参数。执行器回调收到遮蔽后的副本，记录也遮蔽具名与位置形式的
秘密输入。WebRunner 的 `WR_ac_basic_auth` 已使用此 `secret` 参数契约。

`mouse_scroll` 默认改为 `scroll_up`，各平台正值都向上滚动。依赖旧默认向下的 X11
脚本请明确传 `scroll_direction="scroll_down"`。坐标使用 `int(round(value))`，
移动前拒绝 NaN／无限值，包括滚动目标。剪贴板格式描述中缺少的名称统一为空字符串。

其他区域键使用 `oem_1` 至 `oem_8`、`oem_102` 等实体键名，
不保证在所有布局上输入相同字符。

## 图像与 OCR 边界

图像匹配先读取文件字节再解码，因此 Windows 支持非 ASCII 路径。二维数组与
Pillow `L` 模板保留灰度；解码／匹配失败抛出 `ImageNotFoundException`。空白或损坏
的图像文件维持 `read_image` 文档所述的 `ValueError` 契约。OCR 会保留长的左框，
让从框内开始、在下一框结束的短语仍可匹配。

图像及点击中心使用整数向下取整，包含负屏幕坐标。区域截取拒绝空白／非有限矩形，
并与桌面取交集，不将屏幕外像素补黑。`grab_logical` 返回裁切后的左上原点；图像
匹配与 OCR 加上此实际原点。Windows、macOS 全局 point 与 Linux 区域截图共用
此行为。无法预先取得桌面边界时，使用已截取画面的边界。

Jeffrey_RPA 原有拒绝 slash 的测试需要配合已批准的 OEM 快捷键契约更新。
可移植测试迁移补丁位于 `docs/compatibility/jeffrey-rpa-oem-test-migration.patch`；
验证使用测试副本搭配当前的下游代码。等正式 editable 批次停止、整合此分支时再应用。

远程执行采用服务器持有的明确 capability 清单。未知命令需 admin 权限，
provider 的 `readOnly` 提示不会授予权限；保存截图到文件也需 admin。嵌套、载入与流程区块动作在插值及
位置／默认参数绑定后，检查声明的文件路径。并行与延后工作保留调用者身份及允许
根目录；每个远程请求与延后执行都有独立脚本变量。配置的签名及加密密钥也必须位于
有效根目录内，或改用明确的内存密钥。未设置 policy 的本机调用沿用既有行为。
色彩／HSV 与 VLM 结果使用实际裁剪后的捕获原点。Windows 还原接受最小化窗口
回到先前最大化状态。

## 结构化动作日志（Beta）

使用带类型的 `je_auto_control.api.journal` 入口录制动作及读取指定 run。
相同三项操作也提供于门面、`AC_execute_journaled`、`AC_read_action_journal`、
`AC_list_journal_runs`、MCP 与 Script Builder。Run History 的 Actions 菜单提供录制及只读预览。

```python
from je_auto_control.api.journal import execute_journaled, read_action_journal
run = execute_journaled([["AC_sleep", {"seconds": 0}]], "actions.jsonl", run_id="demo")
events = read_action_journal("actions.jsonl", run_id=run["run_id"])
```

Schema 版本 1 分开存储输入与结果，包含 run／step／parent ID、来源文件路径及步骤索引。
开始与结束记录在共享 run 锁内追加；读取时保留开始顺序并汇总各步骤最新状态。
中断步骤维持 `incomplete`。完整 `${secrets.NAME}` 输入引用会保留；秘密字面值在普通 log
或追加日志前遮罩，并标示不可重放。未知 payload 对象省略并附原因，日志序列化不调用其 repr／str。

要明确包覆 executor 调用，可使用 `with ActionJournal(path).run()`。
设置 `JE_AUTOCONTROL_ACTION_JOURNAL` 可启用 executor 自动录制；未设置时沿用既有行为。
读取及预览不执行动作。日志路径及其锁文件遵循有效文件系统 policy。

## 固定画面自愈比较（Beta）

使用 `je_auto_control.api.healing` 比较相同已保存画面的定位版本，数据包含
标注目标框、预期未命中、原点及像素／逻辑缩放。
```python
from je_auto_control.api.healing import compare_healing_versions
report = compare_healing_versions("benchmarks/self_healing/dataset.json", {
    "before": {"template_path": "benchmarks/self_healing/before.png"},
    "after": {"template_path": "benchmarks/self_healing/after.png"}},
    report_path=".test-tmp/healing-report.json")
```

JSON 与 HTML 报告保留 frame hash、期望几何及原始 run／step 来源，列出图像命中、
VLM 尝试、未命中、错误及未知标签。正确率、误判率与恢复率附分子／分母；
p50／p95 对所有尝试采用线性插值。无成本数据时显示 unknown；未标注不算正确，
VLM 猜错不算恢复。历史操作验证与定位结果分开，不能归因于新比较版本。

`create_template_candidate`、`preview_template_candidate`、
`validate_template_candidate`、`accept_template_candidate`、`revert_template_revision`
提供不可变快照及明确审阅。接受前须有正确正例、已标注数据全部正确、无错误／误判，
且原始模板及候选 hash 未改动。预览不应用变更；还原检查当前仍为已接受候选。

六项操作均有对应 `AC_*`、MCP 与 Script Builder。Self-Healing 的 Actions 菜单
通过保留 scope 的后台任务执行比较／修订，面板显示指标、失败及原始步骤表与两张预览。
HealEvent schema 2 保留实际捕获身份、策略耗时、backend／model 及日志 ID，仍可读
旧 schema 1。缺少的证据保持 unknown。版本控制中的合成 benchmark 是离线证据，
实机及付费模型验证分别进行。

## 日志候选脚本产码（Beta）

使用 `je_auto_control.api.codegen` 生成指定 run 的候选：
```python
from pathlib import Path
from je_auto_control.api.codegen import generate_candidate_from_log
candidate = generate_candidate_from_log(Path("benchmarks/journal_codegen/actions.jsonl"), run_id="demo")
print(candidate.code, candidate.manifest, candidate.warnings)
```

产码验证单一日志快照，保留内容 hash、所有 step／parent／source 身份、状态及
已观察到的 retry 次序。仅完成且可重放的叶节点交给现有产码器；失败、中断及
掩码步骤仍留在 manifest 与警告。完整 `${secrets.NAME}` 引用保留，秘密字面值及
结果不转为重放输入；不求值输入 repr，也不执行产物。

候选明确标示为 **observed path only**，按开始顺序串行排列，不重建原本分支／
循环／retry／parallel 语义。检查已安装命令、必要 Python 参数及 executor dry-run，
Python 目标另通过 AST 验证；Robot 的 Python AST 指标不适用。执行或扩展前须审阅。
```powershell
python -m je_auto_control.cli codegen --from-log benchmarks/journal_codegen/actions.jsonl --run-id demo -o .test-tmp/test_observed.py
```

`-o` 保存源代码及 `.manifest.json`、`.actions.json` 附文件，不能覆盖输入日志。
省略时 CLI 将源代码输出至 stdout，警告至 stderr。现有 target／style／name／
failure-bundle 参数可用；日志模式默认 `actions`，普通动作文件仍为 `calls`。
`generate_journal_candidate`、`AC_generate_journal_candidate`、
`ac_generate_journal_candidate` 返回相同结构化 JSON 产物。

Recording Editor 与 Script Builder 的 Actions 提供候选审阅，保留 scope 的后台任务
生成掩码后差异、源代码及来源只读预览。导入是独立编辑操作；导出保存已审阅候选
及附文件。预览与导入均不执行候选动作。`benchmarks/journal_codegen` 合成示例是离线契约证据。

缺少已记录解析绑定的普通 `${var}` 输入会略过并显示警告，避免误用新执行器的变量。
验证也检查 block 命令的对象参数及必填字段。日志对位置参数按签名辨识秘密，
遮罩敏感变量 getter 的返回结果，并将未处理的子步骤失败传到容器／run 状态；
成功捕获或重试处理的失败仍保持成功状态。
插值变量名称在记录前保守视为私密资料。
已辨识的私密标量（包含数值 PIN）也会在结果／日志副本中遮罩。

## 持久化配置服务器（Beta）

信令服务以 SQLite 保存配置 bucket，重启后仍保留。使用 `--config-store PATH`
或 `AC_CONFIG_STORE_PATH`；默认在首次使用时解析为
`~/.je_auto_control/config_sync.sqlite`。导入 API 或创建 app 不会创建数据库。

`PUT /config/{user_id}` 必须传入包含 `schema_version: 2`、`base_revision`、
`operation_id`、`bucket` 的新版 envelope。版本检查与写入在同一事务完成。
GET 返回已提交的 `revision` 及 `cas_supported: true`；过期写入返回 HTTP 409。
相同操作重发返回原提交版本，不覆盖后来的数据；重用 ID 传不同数据会被拒绝。
账号隔离、共享秘密与数据量／账号上限仍有效，浏览器 preflight 支持 PUT。
WebRTC 待配对连接仍采用 TTL。

`je_auto_control.api.config_sync` 提供 `ConfigStore`、`ConfigBucket`、
`ConfigSyncError`、`ConfigRevisionConflict`、`ConfigStoreCapacityError`。
ConfigSyncClient 默认使用受保护的因果同步与持久化 outbox。
明确使用 `SyncClientOptions(legacy_writes=True)` 时，也必须开启服务器的
`--allow-legacy-config-writes` 迁移选项。配置同步页签使用共享受保护服务。

## 因果同步与离线重发（Beta）

使用 `causal_upsert`／`causal_remove` 配合客户端稳定的 `device_id` 编辑定义。
`SyncEntry` 带有版本向量、来源及操作 ID；`merge_entries` 保留并行修改的双方数据，
不依本机时钟选择胜方。`ConfigBucket.entries()` 排除未解决冲突与删除项。
审阅后可明确进行因果编辑解决冲突；旧版时间戳 helpers 仍保留。

`ConfigSyncClient.sync()` 收到确认的 HTTP 409 后重新读取、合并并有限次重试。
SQLite `SyncOutbox` 按 endpoint 与账号保存原 envelope，成功与否不确定时，
重启后仍以原操作 ID 重发。认证仅留在内存；pending、冲突与重试耗尽的数据不丢弃。
`retry_pending(cancel=...)` 使用有限退避并在发送间检查取消；`close()` 释放数据库，
保留队列数据。

共享 `__sync_devices__` 注册表记录确认版本与退休状态。新删除只在 CAS envelope
取得提交版本，所有已知有效设备确认后才回收，不因经过几天而移除。
退休或注册冲突会阻止增量同步及 push；`full_resync()` 明确取得完整受保护快照后再加入。
完整同步前必须审阅待发操作；`retire_device()` 也需明确调用。
本机 `SyncOutbox` peer 接口可跨重启保留退休状态。
目前证据是受控 SQLite／HTTP 测试，实体多机验证仍待完成。

## 定义与资产同步（Beta）

配置同步页签、六个 `AC_config_sync_*`／`ac_config_sync_*` 入口及 Script Builder
共享 headless 的预览、受保护交换、明确应用、持久化重发、本地状态及资产服务。
面板显示提交版本、待发数、保留冲突、离线和 CAS 保护；Actions menu worker
有独立取消事件，在操作之间检查取消，当前有超时限制的请求结束后释放客户端。

本地 JSON 的 `scripts`、`locators`、`hotkeys`、`triggers`、`address_book` 分别
对应 ID／定义对象。未变化的快照保留因果 ID；重建 adapter 时应保存 state mapping。
文件服务把 state 放在明确工作目录，按账号与正常化 endpoint 隔离。命名秘密、
按函数签名绑定的 action 参数、已知秘密回显、认证 URL、绝对机器路径转成本地
`{"$local": "/字段/路径"}` 引用；`${secrets.NAME}` 原样保留。缺少本地引用的
定义列为未解决。任意 Python／源码与未分类 literal 不在此结构化隐私契约内。
接收定义不启动 listener、引擎、连接或脚本。

预览及交换保留全部因果候选，不应用本地定义。应用检查原文件哈希；`choices`
明确选择 `sync_conflict` 数组索引，例如 `{"locators/button": 0}`，解决后推进
全部已知候选的向量。收到的热键／触发器在加入前禁用，禁用热键不进入 listener 快照。

资产清单包含 `path`、`sha256`、`size`。资产入口从明确来源目录接收；Python
`sync_assets` 支持 streaming transport。每文件限制 256 MiB，拒绝越界、symlink
与 Windows 转向文件名，完整大小／哈希验证后才原子替换。取消、损坏或断线只
清除本次临时文件，保留原目标；之前已完成文件保持发布。定义声明的 `assets`
先在定义文件目录下验证才能应用；资产按数据保存，哈希验证不判断内容是否含秘密。

文件夹维持只新增／更新：内容哈希发现同 mtime 修改，连续两次稳定观察后传输，
失败重试且接收文件不回发。停止时保留尚未结束 sender 的所有权。TCP 剪贴板
以有限 origin／event／hash 去重，抑制收到内容的下一次回发，旧 envelope 仍可读。
目前证据为受控 HTTP／SQLite、文件与 offscreen Qt；实体多机验证仍待完成。

## 远程连接所有权（Beta）

Remote Desktop 每个面板独立拥有 TCP、WebSocket、WebRTC 的 host／viewer session。
连接或关闭一个面板会保留其他面板与脚本。callback 保存请求授权与 session generation；
已结束连接的排队画面、状态、传文件与信令结果会丢弃。面板销毁会停止所属传输与
WebRTC 后台工作；清理失败的传输保留在 registry，供明确重试。

24 个传输命令都接受 keyword-only `session_id`。省略时选择该 transport／role 的
script default；新 default 只替换原 default。明确 ID 分配新的具名连接，不改 default；
仍在记录中的已分配 ID 不可重用。原有七个 TCP MCP 工具接受相同 ID，另提供
17 个 WebSocket／WebRTC 和三个生命周期工具。Script Builder 以有限 JSON 编辑输入对象和 region。

`je_auto_control.api.remote_sessions` 导出不可变的 `RemoteSession`、`SessionStatus`
（同一快照类型）、`SessionEvent`、类型化错误、`get_remote_session`、
`disconnect_session`、`list_remote_session_events`。AC／MCP 的 JSON 操作为
`AC_remote_session_status`、`AC_remote_disconnect_session`、`AC_remote_session_events`
和对应小写工具名。optional `owner` 核对所有者；远程授权仍需 `MANAGE_HOSTS`。
事件最多保存 1,024 条，非 default 已关闭 session 保存 256 条；状态和事件不含秘密或资源对象。

session `active` 表示本地分配成功；WebRTC 对端就绪程度用传输的 `authenticated`／`state`
判断。GUI 多 viewer host 状态另含 `peers`／`connected_clients`。session／事件仅存在于
本进程，不是持久化配置同步数据。`disconnect_session(id, owner=...)` 只影响该连接。
当前证据为受控 transport 替身和 offscreen Qt；实体多机验证仍待完成。

## 同步恢复与延后 Apply（Beta）

Exchange 在第一次网络请求前保存尚未发出的本机发布意图。Retry 先与最新的受保护
快照做因果合并，才创建 CAS 请求；Preview 和开始前取消的操作不排入发布意图。
已发出但结果未明的请求保留原 ID 和内容。明确 Retry 可重新尝试耗尽的重发；
只有服务器确认 HTTP 409 的请求才可重新合并并原子替换。未提交的删除 receipt
重新指定到新 CAS revision；每次重新合并前再次验证远端隐私。
本机状态返回 `recovery` 各状态数量，Exchange 用 `recovery_required` 区分需要
恢复的情况与网络离线。

Exchange 和 Retry 不修改本机定义。收到预览不代表已应用：只有明确 Apply 解决
全部项目与必要资源／引用后才推进 `applied_revision`，下一次 Exchange 才发布
该确认。未解决项目仍保留删除义务，因此延后 Apply 不会让已回收数据复活。
直接因果 client 默认确认返回快照；需要明确本机应用的 adapter 使用
`SyncClientOptions(acknowledge_on_sync=False)`。只有同一因果删除的 receipt 数据
会合并；独立编辑或不同 JSON 值仍需冲突审阅。

Quick Connect 在最后交付画面、错误和光标时检查 session generation；WebRTC
视频切换使用相同保护，停止、替换和认证成功会撤销预约重连。文件夹同步保留
仍在结束中的传送者，等停止后才允许重启。旧剪贴板只抑制连续相同内容，允许
A→B→A；新版仍以有限事件 ID 去重，并抑制一次收到内容的回传。
证据来自受控 SQLite／网络边界和 offscreen Qt；实体多机验证仍待完成。

### 移动 App 生命周期与可选 adapter

`launch_app`、`wait_for_app`、`app_state`、`stop_app` 与 `handle_mobile_alert`
使用明确 session、返回观察到的状态，请求有时限且轮询可取消。
iOS App 操作创建 WDA session ID，只删除该 ID；删除可能终止它的 App。
Android 关闭连接仍让 App 运行，需要明确 `stop_app`；清理失败可重试 `close()`。
`MobileExtensionSpec` 以被动能力信息配置单一 owner 的延迟 factory。
Android 提供 APK 安装、push/pull 与 SDK Unicode 剪贴板。
iOS 安装／文件／剪贴板，以及双平台录屏需要拥有资源的 `MobileExtension`；
缺少 adapter 报告 `needs_dependency` 及修复方式。
`mobile_app`、`mobile_alert`、`mobile_extension_action` 共用 AC/MCP/Builder
及 Device Matrix Actions；日志遮罩 extension options／结果。
[App 示例](../examples/mobile_app_lifecycle.py) 默认被动，`--run` 才操作。
原生 emulator/WDA 授权与恢复仍列 H3 验收。

WDA App 操作需要专用空闲 endpoint：有时限的 status 检查拒绝既有／未知 session，本进程 lease 防止同 URL 同时创建 owner。WDA 无法原子排除外部 client 或 endpoint 别名，请保持该 endpoint 专用。

### 移动设备工作区与原生冒烟测试

Mobile 移动设备标签页保留同一 owner，供 App、截图与输入操作共用。
选择平台、序列号／WDA URL 与超时，通过 Actions → 打开设备 owner 开始。
检查依赖不连接；检查连接／授权才发送 get-state 或 WDA GET /status。
执行所选操作共用 `AC_android_mobile_action`／`AC_ios_mobile_action`、MCP 与
Builder 的 13 项操作目录。执行设备操作先验证整个平坦的设备专用列表；
关闭设备 owner 立即撤销输入，并在后台清理。`mobile_surface_matrix()` 对照所有
executor 命令，并提供桌面专用操作的设备替代方案。自动日志屏蔽设备扩展结果，
显式调用方仍能取得结果。

用 `python -m pip install uiautomator2==3.7.0 facebook-wda==1.5.4` 安装可选 SDK；
Android 还需要 Android SDK platform-tools、USB 调试及 RSA 授权。
iOS 需要 Apple 主机／设备上已签名的 WebDriverAgentRunner、开发者模式及专用空闲 WDA
endpoint。参阅[移动设备设置](../docs/MOBILE_SETUP.md)。
`python examples/mobile_device_smoke.py --validate` 无需硬件；`--connect` 启用连接诊断，
`--exercise --app-id ...` 还会启动、截图并停止指定测试 App。已提供 Android 14
Docker/KVM 配置及手动原生 CI；测试配置与受控测试不等于实体设备验证。

### 延迟创建 GUI 面板

启动只创建录制、Script Builder 与远程桌面。完整 50 个标签页仍可通过 View → Tabs
打开；其他功能首次打开时才导入及创建，Actions 也在创建后绑定。
保留 `show_tab`、`hide_tab`、`list_registered_tabs` 接口；隐藏保留输入内容，
标签页关闭按钮及 `close_tab` 释放面板与订阅。重新打开已关闭页面以同一 key 创建新 widget。
切换语言／更新引擎只处理已创建面板；缺少可选依赖显示恢复说明。
GUI factory 在 GUI 线程执行；registry 的 headless metadata 不导入 Qt 或功能模块。

### 可搜索工作区与主题

左侧导航可搜索全部 50 个功能 key、翻译标题及英文别名，搜索不会打开面板。
Ctrl+K 聚焦搜索，Enter 打开第一个匹配项。中央工作区保留现有分页及 Actions
菜单；右侧执行详情显示明确报告的状态、原因、恢复方式及进度；工作区就绪不代表
原生权限已验证。Ctrl+Shift+D 或 View 可切换详情，宽度小于 900 逻辑像素时默认
折叠；较宽内容可通过滚动条操作。View → 主题切换深色／浅色，字号及四种语言切换
会保留搜索和面板输入。主题使用系统字体及原生 Qt 图标。
[Qt 布局截图](../benchmarks/results/gui-workspace-f2/report.json)记录 offscreen 条件，
不代表原生设备或混合 DPI 验证。

### GUI 工作与取消

Actions → 取消当前工作会停止当前面板的嵌套动作与等待；关闭面板会撤销延迟结果。
较慢的设备、截图、识别、网络及服务停止操作在 Qt 外执行。截止时间采用协作方式：
已开始的原生调用须在后端时限内返回。取消不能恢复已完成的文件、保险库或全局
服务变更；共享服务器／引擎仍需明确执行 Stop。Tools → 重试自有清理可重试保留的
失败项目。GUI 录制持有独立录制器／订阅，不会停止全局录制。
GUI 的原始按键／鼠标按钮持有可跨成功工作保留，取消或销毁面板时释放自有持有；
保留原先已按住的输入，无法确认初始键态时在分配前拒绝持有。这不是跨 client 的
原子保护，也不代表实体状态已恢复。直接 headless 调用沿用既有行为。
请参阅[工作生命周期与 I/O 审核](../docs/GUI_TASK_LIFECYCLE.md)。
