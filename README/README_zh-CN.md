# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** 是一套跨平台的 Python GUI 自动化框架。它能驱动鼠标与键盘、在画面上找到目标
（模板匹配、OCR、操作系统无障碍树，或视觉模型）、录制与回放操作流程，并以 JSON 动作文件执行——
支持 Windows、macOS、Linux（X11 与 Wayland）、Android 与 iOS。

每项能力都以三种形式提供：**Python API**、可在 JSON 文件／CLI／服务器使用的 **`AC_*` 动作命令**，
以及 **GUI 标签页**。没有任何功能只存在于 GUI。

**[English](../README.md)** · **[繁體中文](README_zh-TW.md)**

---

## 为什么选择 AutoControl

- **一套 API，六个平台。** `wrapper/platform_wrapper.py` 在导入时挑选后端；同一份脚本在
  Windows、macOS、X11 与 Wayland 上都不需要改写。
- **不写 Python 也能脚本化。** 773 个 `AC_*` 命令覆盖全部功能，因此一个 JSON 文件能做到库
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

**系统需求：** Python ≥ 3.10。Linux 请先安装构建依赖：

```bash
sudo apt-get install cmake libssl-dev
```

OCR、VLM 与 LLM 后端（`pytesseract`、`easyocr`、`paddleocr`、`anthropic`、`openai`）
都是按需加载——只装你实际会用到的。

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
python -m je_auto_control          # 或：je_auto_control.start_autocontrol_gui()
```

录制一段流程、在可视化 Script Builder 里编辑，然后存成 CLI 能直接执行的同一种 JSON 格式。

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
| JSON 脚本 | `execute_action`、`execute_files` | 全部 773 个命令 | Script、Script Builder |
| 变量与流程控制 | `execute_action_with_vars` | `AC_set_var`、`AC_loop`、`AC_for_each`、`AC_try`、`AC_retry` | Variables |
| 数据驱动执行 | — | `AC_for_each_row`（CSV／JSON／SQLite／Excel） | Data Sources |
| 断言 | `assert_text`、`assert_image` | `AC_assert_text` 等 21 个 | Assertions |
| 测试套件 | `run_suite` | `AC_run_suite` | Test Suites |
| 调度（间隔 + cron） | `default_scheduler` | — | Scheduler |
| 全局热键 | `default_hotkey_daemon` | — | Hotkeys |
| 事件触发 | `default_trigger_engine` | `AC_email_trigger_add` | Triggers、Webhooks、Email |
| 窗口管理 *(仅 Windows)* | `list_windows`、`focus_window` | `AC_focus_window`、`AC_snap_window` | Window Manager |
| 剪贴板（文本 + 图片） | `get_clipboard`、`set_clipboard`、`get_clipboard_image`、`set_clipboard_image` | `AC_clipboard_get`、`AC_clipboard_set`、`AC_clipboard_get_image`、`AC_clipboard_set_image` | — |
| 远程桌面 | `RemoteDesktopHost`、`RemoteDesktopViewer` | `AC_start_remote_host`、`AC_remote_connect` | Remote Desktop |
| USB 枚举与直通 | `list_usb_devices`、`enable_usb_passthrough` | `AC_usb_*`（16 个命令） | USB Devices、USB Share |
| 密钥保险库 | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| 报表（HTML／JSON／XML） | `generate_html_report` | `AC_generate_html_report` | Report |
| 运行历史 | — | — | Run History |
| 指标与追踪 | `default_metric_registry`、`render_metrics_text` | — | — |
| 系统诊断 | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| 测试代码生成 | `generate_code` | — | — |

除了这张表，`utils/` 下还有 308 个无头包，覆盖断言、韧性、数据质量、i18n 审计、脱敏、
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
旧版 `python -m je_auto_control -e file.json` 入口仍然可用。

---

## 服务器与集成

| 接口 | 启动方式 | 说明 |
|---|---|---|
| **MCP 服务器** | `je_auto_control_mcp`（stdio）或 `AC_start_mcp_http_server` | 676 个工具，供 Claude Desktop／Claude Code／自定义 tool loop 使用。Bearer 认证、TLS、审计日志、限流、插件热重载、CI 假后端。 |
| **REST API** | `je_auto_control start-rest` | Bearer token、按 IP 限流与锁定、SQLite 审计 hook、`/metrics`、`/openapi.json`、`/docs` Swagger UI、`/dashboard`。 |
| **TCP socket 服务器** | `je_auto_control start-server` | 以换行分隔的 JSON 动作列表。默认绑定 `127.0.0.1`。 |
| **pytest 插件** | 安装后自动生效 | 提供 fixture 与供 pytest-bdd／behave 使用的 Gherkin step library。 |
| **语言服务器** | `python -m autocontrol_lsp.server` | 为 `AC_*` 动作 JSON 提供补全与诊断，命令清单直接取自运行期的命令表。 |
| **远程桌面** | `RemoteDesktopHost` 或 GUI | TCP、WebSocket 或 WebRTC；TOTP、信任列表、TURN 配置、文件／剪贴板／音频同步。 |

除非明确指定，所有服务器都绑定在 `127.0.0.1`。

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
| macOS 10.15+ | pyobjc / Quartz | ✅ | ✅ | ❌ | ❌ |
| Linux X11 | python-Xlib（可选 `uinput`） | ✅ | ✅ | ✅ | ❌ |
| Linux Wayland | libei，或 ydotool／wtype／grim | ✅ | ✅ | ❌ | ❌ |
| Android | adb + uiautomator2 | ✅ | ✅ | — | — |
| iOS | WebDriverAgent / facebook-wda | ✅ | ✅ | — | — |

Wayland 禁止非特权客户端进行全局输入录制——若要录制，请设置
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` 并在 X11 会话下运行。窗口管理目前仅
Windows 有实现，其他平台会抛出明确的 `NotImplementedError`。对于会忽略合成输入的应用，
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
| [WHATS_NEW.md](../WHATS_NEW.md) | 各版本更新说明。 |
| [CHANGELOG.md](../CHANGELOG.md) | 兼容性变更记录。 |
| [SECURITY.md](../SECURITY.md) | 安全策略与报告方式。 |

---

## 开发

```bash
git clone https://github.com/Intergration-Automation-Testing/AutoControl.git
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

- **主页**：https://github.com/Intergration-Automation-Testing/AutoControl
- **PyPI**：https://pypi.org/project/je_auto_control/
- **文档**：https://autocontrol.readthedocs.io/en/latest/
