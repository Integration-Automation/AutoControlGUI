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
- **不写 Python 也能脚本化。** 792 个 `AC_*` 命令覆盖全部功能，因此一个 JSON 文件能做到库
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
| `gui` | PySide6 桌面应用（48 个标签页） |
| `webrtc` | WebRTC 远程桌面、USB 直通（`aiortc`、`av`） |
| `signaling` | 独立的信令／rendezvous 服务器（`fastapi`、`uvicorn`） |
| `discovery` | mDNS / Zeroconf 局域网主机发现 |
| `pdf` / `office` | PDF 与 Excel／Word／PowerPoint 读取 |
| `fuzzy` / `locale` | `rapidfuzz` 模糊匹配、`babel` 区域解析 |
| `s3` / `audio` | S3 制品存储、系统音量控制 |

**Windows arm64** 装得起来也跑得起来，少的是上游在那里发不出来的那些：
`opencv-python` 与 `cryptography` 都没发 `win_arm64` wheel。所以 `find_image*`、
`screenshot()`（OpenCV／BGR 那一支——Pillow 截图仍可用）、密钥金库、动作文件加密、
ACME／TLS 与加密录影会抛出指名缺哪个 wheel 的错误，而不是难以追查的失败。
鼠标、键盘、屏幕尺寸、窗口管理、无障碍树、动作执行器、MCP／REST／TCP 服务器
与 GUI 都正常——这是实测的，不是推论的。其他平台不受影响。

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
| JSON 脚本 | `execute_action`、`execute_files` | 全部 792 个命令 | Script、Script Builder |
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
| **MCP 服务器** | `je_auto_control_mcp`（stdio）或 `AC_start_mcp_http_server` | 697 个工具，供 Claude Desktop／Claude Code／自定义 tool loop 使用。除了以 `initialize` 握手的各版协议，也支持无状态的 MCP 2026-07-28。Bearer 认证、TLS、审计日志、限流、插件热重载、CI 假后端。 |
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

¹ macOS 的录制走 Quartz event tap，需要**辅助功能**权限
（系统设置 → 隐私与安全性 → 辅助功能）。没有授权时会直接抛出并指名
缺的是哪个权限，而不是安静地录到一个空的 session。

² BSD 直接跑同一套 X11 后端——同一个 X server、同一个 `python-Xlib`，而输入、
录制与窗口管理就只依赖这一个包。`freebsd` CI job 在真的 FreeBSD 14 上驱动真的
输入，再从 X server 读回来；OpenBSD 与 NetBSD 走同一条代码路径，只是没有 CI
runner。唯一的例外是屏幕截取，卡住的是打包而不是平台：它走 Pillow／mss 与
OpenCV，而 `opencv-python`、`pillow`、`cryptography` 都没有发 FreeBSD wheel。
从 ports 构建之后，截取、图像匹配、OCR 与动作加密也都能用——
`import je_auto_control` 本身已经不需要它们任何一个。

Wayland 的输入在 libei 走不通时会退回 `ydotool` CLI，而这条退路需要
**ydotool 1.0 以上**。AutoControl 送的每一个参数都是那一版才有的；0.1.x
（Debian bookworm 与目前所有 Ubuntu 仍以这个名字提供，Debian trixie 则根本没有）
对同一批参数返回 0 却不送出任何事件。AutoControl 会检测并直接拒绝，
而不是为根本没送出的输入回报成功。Arch、Fedora 与 Debian unstable 提供的是 1.0。

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

Wayland 禁止非特权客户端进行全局输入录制——若要录制，请设置
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` 并在 X11 会话下运行。窗口管理支持
Windows、macOS（pyobjc）与 X11（含 XWayland）；纯 Wayland 会话的协议不让客户端看到其他程序的窗口，
所以 `list_windows()` 返回空列表，其余窗口操作一律抛出带原因的 `AutoControlUnsupportedOperationException`。对于会忽略合成输入的应用，
可选用驱动层后端（`JE_AUTOCONTROL_WIN32_BACKEND=interception`、
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`、ViGEm 虚拟手柄）；驱动未安装时会自动回退到原有行为。

---

## 文档与示例

| 资源 | 内容 |
|---|---|
| [`examples/`](../examples/) | 27 个自包含脚本：截图点击、OCR、调度器、远程桌面、agent loop、可观测性、录制、变量、热键、触发器、报表、MCP、REST、密钥、插件、computer use、Wayland、跨主机 DAG、chat-ops、pytest/BDD、锚点定位。 |
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
