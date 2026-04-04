# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)

**AutoControl** 是一個跨平台的 Python GUI 自動化框架，提供滑鼠控制、鍵盤輸入、圖像辨識、螢幕擷取、腳本執行與報告產生等功能 — 透過統一的 API 在 Windows、macOS 和 Linux (X11) 上運作。

**[English](../README.md)** | **[简体中文](README_zh-CN.md)**

---

## 目錄

- [功能特色](#功能特色)
- [架構](#架構)
- [安裝](#安裝)
- [系統需求](#系統需求)
- [快速開始](#快速開始)
- [API 參考](#api-參考)
  - [滑鼠控制](#滑鼠控制)
  - [鍵盤控制](#鍵盤控制)
  - [圖像辨識](#圖像辨識)
  - [螢幕操作](#螢幕操作)
  - [動作錄製與回放](#動作錄製與回放)
  - [JSON 腳本執行器](#json-腳本執行器)
  - [報告產生](#報告產生)
  - [遠端自動化（Socket 伺服器）](#遠端自動化socket-伺服器)
  - [Shell 命令執行](#shell-命令執行)
  - [螢幕錄製](#螢幕錄製)
  - [回呼執行器](#回呼執行器)
  - [套件管理器](#套件管理器)
  - [專案管理](#專案管理)
  - [視窗管理](#視窗管理)
  - [GUI 應用程式](#gui-應用程式)
- [命令列介面](#命令列介面)
- [平台支援](#平台支援)
- [開發](#開發)
- [授權條款](#授權條款)

---

## 功能特色

- **滑鼠自動化** — 移動、點擊、按下、釋放、拖曳、滾動，支援精確座標控制
- **鍵盤自動化** — 按下/釋放單一按鍵、輸入字串、組合鍵、按鍵狀態偵測
- **圖像辨識** — 使用 OpenCV 模板匹配在螢幕上定位 UI 元素，支援可設定的偵測閾值
- **截圖與螢幕錄製** — 擷取全螢幕或指定區域為圖片，錄製螢幕為影片（AVI/MP4）
- **動作錄製與回放** — 錄製滑鼠/鍵盤事件並重新播放
- **JSON 腳本執行** — 使用 JSON 動作檔案定義並執行自動化流程
- **報告產生** — 將測試紀錄匯出為 HTML、JSON 或 XML 報告，包含成功/失敗狀態
- **遠端自動化** — 啟動 TCP Socket 伺服器，接收並執行來自遠端客戶端的自動化命令
- **Shell 整合** — 在自動化流程中執行 Shell 命令，支援非同步輸出擷取
- **回呼執行器** — 觸發自動化函式後自動呼叫回呼函式，實現操作串接
- **動態套件載入** — 在執行時匯入外部 Python 套件，擴充執行器功能
- **專案與範本管理** — 快速建立包含 keyword/executor 目錄結構的自動化專案
- **視窗管理** — 直接將鍵盤/滑鼠事件送至指定視窗（Windows/Linux）
- **GUI 應用程式** — 內建 PySide6 圖形介面，支援互動式自動化操作
- **跨平台** — 統一 API，支援 Windows、macOS、Linux（X11）

---

## 架構

```
je_auto_control/
├── wrapper/                    # 平台無關 API 層
│   ├── platform_wrapper.py     # 自動偵測作業系統並載入對應後端
│   ├── auto_control_mouse.py   # 滑鼠操作
│   ├── auto_control_keyboard.py# 鍵盤操作
│   ├── auto_control_image.py   # 圖像辨識（OpenCV 模板匹配）
│   ├── auto_control_screen.py  # 截圖、螢幕大小、像素顏色
│   └── auto_control_record.py  # 動作錄製/回放
├── windows/                    # Windows 專用後端（Win32 API / ctypes）
├── osx/                        # macOS 專用後端（pyobjc / Quartz）
├── linux_with_x11/             # Linux 專用後端（python-Xlib）
├── gui/                        # PySide6 GUI 應用程式
└── utils/
    ├── executor/               # JSON 動作執行引擎
    ├── callback/               # 回呼函式執行器
    ├── cv2_utils/              # OpenCV 截圖、模板匹配、影片錄製
    ├── socket_server/          # TCP Socket 伺服器（遠端自動化）
    ├── shell_process/          # Shell 命令管理器
    ├── generate_report/        # HTML / JSON / XML 報告產生器
    ├── test_record/            # 測試動作紀錄
    ├── json/                   # JSON 動作檔案讀寫
    ├── project/                # 專案建立與範本
    ├── package_manager/        # 動態套件載入
    ├── logging/                # 日誌紀錄
    └── exception/              # 自訂例外類別
```

`platform_wrapper.py` 模組會自動偵測目前的作業系統並匯入對應的後端，因此所有 wrapper 函式在不同平台上的行為完全一致。

---

## 安裝

### 基本安裝

```bash
pip install je_auto_control
```

### 安裝 GUI 支援（PySide6）

```bash
pip install je_auto_control[gui]
```

### Linux 前置需求

在 Linux 上安裝前，請先安裝以下系統套件：

```bash
sudo apt-get install cmake libssl-dev
```

---

## 系統需求

- **Python** >= 3.10
- **pip** >= 19.3

### 相依套件

| 套件 | 用途 |
|---|---|
| `je_open_cv` | 圖像辨識（OpenCV 模板匹配） |
| `pillow` | 截圖擷取 |
| `mss` | 快速多螢幕截圖 |
| `pyobjc` | macOS 後端（在 macOS 上自動安裝） |
| `python-Xlib` | Linux X11 後端（在 Linux 上自動安裝） |
| `PySide6` | GUI 應用程式（選用，使用 `[gui]` 安裝） |
| `qt-material` | GUI 主題（選用，使用 `[gui]` 安裝） |

---

## 快速開始

### 滑鼠控制

```python
import je_auto_control

# 取得目前滑鼠位置
x, y = je_auto_control.get_mouse_position()
print(f"滑鼠位置: ({x}, {y})")

# 移動滑鼠到指定座標
je_auto_control.set_mouse_position(500, 300)

# 在目前位置左鍵點擊（使用按鍵名稱）
je_auto_control.click_mouse("mouse_left")

# 在指定座標右鍵點擊
je_auto_control.click_mouse("mouse_right", x=800, y=400)

# 向下滾動
je_auto_control.mouse_scroll(scroll_value=5)
```

### 鍵盤控制

```python
import je_auto_control

# 按下並釋放單一按鍵
je_auto_control.type_keyboard("a")

# 逐字輸入整個字串
je_auto_control.write("Hello World")

# 組合鍵（例如 Ctrl+C）
je_auto_control.hotkey(["ctrl_l", "c"])

# 檢查某個按鍵是否正在被按下
is_pressed = je_auto_control.check_key_is_press("shift_l")
```

### 圖像辨識

```python
import je_auto_control

# 在螢幕上找出所有符合的圖像
positions = je_auto_control.locate_all_image("button.png", detect_threshold=0.9)
# 回傳: [[x1, y1, x2, y2], ...]

# 找出單一圖像並取得其中心座標
cx, cy = je_auto_control.locate_image_center("icon.png", detect_threshold=0.85)
print(f"找到位置: ({cx}, {cy})")

# 找出圖像並自動點擊
je_auto_control.locate_and_click("submit_button.png", mouse_keycode="mouse_left")
```

### 截圖

```python
import je_auto_control

# 擷取全螢幕截圖並儲存
je_auto_control.pil_screenshot("screenshot.png")

# 擷取指定區域的截圖 [x1, y1, x2, y2]
je_auto_control.pil_screenshot("region.png", screen_region=[100, 100, 500, 400])

# 取得螢幕解析度
width, height = je_auto_control.screen_size()

# 取得指定座標的像素顏色
color = je_auto_control.get_pixel(500, 300)
```

### 動作錄製與回放

```python
import je_auto_control
import time

# 開始錄製滑鼠和鍵盤事件
je_auto_control.record()

time.sleep(10)  # 錄製 10 秒

# 停止錄製並取得動作列表
actions = je_auto_control.stop_record()

# 重新播放錄製的動作
je_auto_control.execute_action(actions)
```

### JSON 腳本執行器

建立 JSON 動作檔案（`actions.json`）：

```json
[
    ["AC_set_mouse_position", {"x": 500, "y": 300}],
    ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
    ["AC_write", {"write_string": "Hello from AutoControl"}],
    ["AC_screenshot", {"file_path": "result.png"}],
    ["AC_hotkey", {"key_code_list": ["ctrl_l", "s"]}]
]
```

執行方式：

```python
import je_auto_control

# 從檔案執行
je_auto_control.execute_action(je_auto_control.read_action_json("actions.json"))

# 或直接從列表執行
je_auto_control.execute_action([
    ["AC_set_mouse_position", {"x": 100, "y": 200}],
    ["AC_click_mouse", {"mouse_keycode": "mouse_left"}]
])
```

**可用的動作命令：**

| 類別 | 命令 |
|---|---|
| 滑鼠 | `AC_click_mouse`, `AC_set_mouse_position`, `AC_get_mouse_position`, `AC_press_mouse`, `AC_release_mouse`, `AC_mouse_scroll`, `AC_mouse_left`, `AC_mouse_right`, `AC_mouse_middle` |
| 鍵盤 | `AC_type_keyboard`, `AC_press_keyboard_key`, `AC_release_keyboard_key`, `AC_write`, `AC_hotkey`, `AC_check_key_is_press` |
| 圖像 | `AC_locate_all_image`, `AC_locate_image_center`, `AC_locate_and_click` |
| 螢幕 | `AC_screen_size`, `AC_screenshot` |
| 錄製 | `AC_record`, `AC_stop_record` |
| 報告 | `AC_generate_html`, `AC_generate_json`, `AC_generate_xml`, `AC_generate_html_report`, `AC_generate_json_report`, `AC_generate_xml_report` |
| 專案 | `AC_create_project` |
| Shell | `AC_shell_command` |
| 程序 | `AC_execute_process` |
| 執行器 | `AC_execute_action`, `AC_execute_files` |

### 報告產生

```python
import je_auto_control

# 先啟用測試紀錄
je_auto_control.test_record_instance.set_record_enable(True)

# ... 執行自動化動作 ...
je_auto_control.set_mouse_position(100, 200)
je_auto_control.click_mouse("mouse_left")

# 產生報告
je_auto_control.generate_html_report("test_report")   # -> test_report.html
je_auto_control.generate_json_report("test_report")   # -> test_report.json
je_auto_control.generate_xml_report("test_report")    # -> test_report.xml

# 或取得報告內容為字串
html_string = je_auto_control.generate_html()
json_string = je_auto_control.generate_json()
xml_string = je_auto_control.generate_xml()
```

報告內容包含：每個紀錄動作的函式名稱、參數、時間戳記及例外資訊（如有）。HTML 報告中成功的動作以青色顯示，失敗的動作以紅色顯示。

### 遠端自動化（Socket 伺服器）

啟動 TCP 伺服器，接收來自遠端客戶端的 JSON 自動化命令：

```python
import je_auto_control

# 啟動伺服器（預設：localhost:9938）
server = je_auto_control.start_autocontrol_socket_server(host="localhost", port=9938)

# 伺服器在背景執行緒中運行
# 透過 TCP 發送 JSON 動作命令即可遠端執行
# 發送 "quit_server" 關閉伺服器
```

客戶端範例：

```python
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("localhost", 9938))

# 發送自動化命令
command = json.dumps([
    ["AC_set_mouse_position", {"x": 500, "y": 300}],
    ["AC_click_mouse", {"mouse_keycode": "mouse_left"}]
])
sock.sendall(command.encode("utf-8"))

# 接收回應
response = sock.recv(8192).decode("utf-8")
print(response)
sock.close()
```

### Shell 命令執行

```python
import je_auto_control

# 使用預設的 Shell 管理器
je_auto_control.default_shell_manager.exec_shell("echo Hello")
je_auto_control.default_shell_manager.pull_text()  # 輸出擷取的結果

# 或建立自訂的 ShellManager
shell = je_auto_control.ShellManager(shell_encoding="utf-8")
shell.exec_shell("ls -la")
shell.pull_text()
shell.exit_program()
```

### 螢幕錄製

```python
import je_auto_control
import time

# 方法一：ScreenRecorder（管理多個錄影）
recorder = je_auto_control.ScreenRecorder()
recorder.start_new_record(
    recorder_name="my_recording",
    path_and_filename="output.avi",
    codec="XVID",
    frame_per_sec=30,
    resolution=(1920, 1080)
)
time.sleep(10)
recorder.stop_record("my_recording")

# 方法二：RecordingThread（簡易單一錄影，輸出 MP4）
recording = je_auto_control.RecordingThread(video_name="my_video", fps=20)
recording.start()
time.sleep(10)
recording.stop()
```

### 回呼執行器

執行自動化函式後自動觸發回呼函式：

```python
import je_auto_control

def my_callback():
    print("動作完成！")

# 執行 set_mouse_position 後呼叫 my_callback
je_auto_control.callback_executor.callback_function(
    trigger_function_name="AC_set_mouse_position",
    callback_function=my_callback,
    x=500, y=300
)

# 帶有參數的回呼
def on_done(message):
    print(f"完成: {message}")

je_auto_control.callback_executor.callback_function(
    trigger_function_name="AC_click_mouse",
    callback_function=on_done,
    callback_function_param={"message": "點擊完成"},
    callback_param_method="kwargs",
    mouse_keycode="mouse_left"
)
```

### 套件管理器

在執行時動態載入外部 Python 套件到執行器中：

```python
import je_auto_control

# 將套件的所有函式/類別加入執行器
je_auto_control.package_manager.add_package_to_executor("os")

# 現在可以在 JSON 動作腳本中使用 os 函式：
# ["os_getcwd", {}]
# ["os_listdir", {"path": "."}]
```

### 專案管理

快速建立包含範本檔案的專案目錄結構：

```python
import je_auto_control

# 建立專案結構
je_auto_control.create_project_dir(project_path="./my_project", parent_name="AutoControl")

# 會建立以下結構：
# my_project/
# └── AutoControl/
#     ├── keyword/
#     │   ├── keyword1.json        # 範本動作檔案
#     │   ├── keyword2.json        # 範本動作檔案
#     │   └── bad_keyword_1.json   # 錯誤處理範本
#     └── executor/
#         ├── executor_one_file.py  # 執行單一檔案範例
#         ├── executor_folder.py    # 執行資料夾範例
#         └── executor_bad_file.py  # 錯誤處理範例
```

### 視窗管理

直接將事件送至指定視窗（僅限 Windows 和 Linux）：

```python
import je_auto_control

# 透過視窗標題送出鍵盤事件
je_auto_control.send_key_event_to_window("Notepad", keycode="a")

# 透過視窗 handle 送出滑鼠事件
je_auto_control.send_mouse_event_to_window(window_handle, mouse_keycode="mouse_left", x=100, y=50)
```

### GUI 應用程式

啟動內建圖形介面（需安裝 `[gui]` 擴充）：

```python
import je_auto_control
je_auto_control.start_autocontrol_gui()
```

或透過命令列：

```bash
python -m je_auto_control
```

---

## 命令列介面

AutoControl 可直接從命令列使用：

```bash
# 執行單一動作檔案
python -m je_auto_control -e actions.json

# 執行目錄中所有動作檔案
python -m je_auto_control -d ./action_files/

# 直接執行 JSON 字串
python -m je_auto_control --execute_str '[["AC_screenshot", {"file_path": "test.png"}]]'

# 建立專案範本
python -m je_auto_control -c ./my_project
```

---

## 平台支援

| 平台 | 狀態 | 後端 | 備註 |
|---|---|---|---|
| Windows 10 / 11 | 支援 | Win32 API (ctypes) | 完整功能支援 |
| macOS 10.15+ | 支援 | pyobjc / Quartz | 不支援動作錄製；不支援 `send_key_event_to_window` / `send_mouse_event_to_window` |
| Linux（X11） | 支援 | python-Xlib | 完整功能支援 |
| Linux（Wayland） | 尚未支援 | — | 未來版本可能加入支援 |
| Raspberry Pi 3B / 4B | 支援 | python-Xlib | 在 X11 上運行 |

---

## 開發

### 環境設定

```bash
git clone https://github.com/Intergration-Automation-Testing/AutoControl.git
cd AutoControl
pip install -r dev_requirements.txt
```

### 執行測試

```bash
# 單元測試
python -m pytest test/unit_test/

# 整合測試
python -m pytest test/integrated_test/
```

### 專案連結

- **首頁**: https://github.com/Intergration-Automation-Testing/AutoControl
- **文件**: https://autocontrol.readthedocs.io/en/latest/
- **PyPI**: https://pypi.org/project/je_auto_control/

---

## 授權條款

[MIT License](../LICENSE) © JE-Chen
