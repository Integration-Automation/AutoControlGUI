============================================================
USB Passthrough — 操作員指南
============================================================

實際把 host 機器上的 USB 裝置借給遠端 viewer 用的步驟手冊。對應
Phase 2a.1（目前已 ship 狀態）— host 端在 Linux libusb 上端到端
運作；Windows WinUSB 為硬體未驗證；macOS IOKit 尚未實作。

如果你是安全審查者而非操作員，請看
:doc:`usb_passthrough_security_review`\ 。如果你想要協定細節，
請看 :doc:`usb_passthrough_design`\ 。

.. contents::
   :local:
   :depth: 2


前置需求
========

在 **host**\ （有實體 USB 裝置的機器）上：

- Python 3.10+ 並安裝 AutoControl。
- 選用的 ``webrtc`` 套件：``pip install je_auto_control[webrtc]``\ 。
- 如要使用 libusb backend 需安裝 ``pyusb``\ ：
  ``pip install pyusb``\ 。
- 預計給 viewer 用的 USB 裝置已插上。
- 各 OS 設定（見下方 *driver 設定*\ ）。

在 **viewer**\ （將使用該裝置的遠端機器）上：

- Python 3.10+ 並安裝 AutoControl。
- 能連到 host 的 REST API port（預設 9939），**且** 在 NAT 後方時
  能連到 WebRTC signalling / TURN 端點。
- host 的 bearer token（操作員以帶外管道交付）。


Driver 設定（依 OS）
====================

Linux（libusb）
---------------

libusb backend 是目前最完整測試過的路徑。步驟：

1. 安裝 ``libusb-1.0`` 開發檔（例如 ``apt install libusb-1.0-0``\ ）。
2. 加上 ``udev`` rule，讓 AutoControl host 程序不需要 root 就能 claim
   裝置。例：YubiKey 5（vendor ``1050``、product ``0407``\ ）::

       # /etc/udev/rules.d/99-autocontrol-usb.rules
       SUBSYSTEM=="usb", ATTRS{idVendor}=="1050",
         ATTRS{idProduct}=="0407", MODE="0660",
         GROUP="plugdev"

   接著 ``sudo udevadm control --reload && sudo udevadm trigger``\ 。
3. 確認 AutoControl 使用者在 ``plugdev`` 群組。
4. 若裝置是 HID，AutoControl 的 libusb wrapper 會在 ``open`` 時 detach
   ``usbhid``\ ，``close`` 時 re-attach。所以在 claim HID 裝置時
   你的本機鍵盤輸入可能會短暫停頓，這是正常。

Windows（WinUSB）— *硬體未驗證*
-------------------------------

ctypes 接線已寫但尚未對實體硬體驗證。視為 alpha。步驟：

1. 用 `Zadig <https://zadig.akeo.ie/>`_ 或 libwdi 把目標裝置綁到
   WinUSB driver。**不要** 對 host OS 已經管理的裝置做這件事
   （印表機、hub、鍵盤）。
2. 綁好後裝置應該會出現在 ``WinusbBackend().list()`` 中。
3. 在依賴 transfer 之前需要硬體測試。期待的測試矩陣見安全審查清單。

macOS（IOKit）— *尚未實作*
--------------------------

骨架已存在；``IokitBackend()`` 可以建構，但 ``list`` / ``open``
會拋 ``NotImplementedError``\ 。請追蹤 Phase 2c。


啟用 feature
============

USB passthrough **預設 off**\ 。兩種開啟方式：

- 環境變數，於程序啟動時讀取::

      export JE_AUTOCONTROL_USB_PASSTHROUGH=1
      python -m je_auto_control.cli start-rest

- 程式控（覆蓋環境變數），於你的 bootstrap 腳本中::

      from je_auto_control.utils.usb.passthrough import enable_usb_passthrough
      enable_usb_passthrough(True)

確認用 :func:`is_usb_passthrough_enabled`::

      from je_auto_control.utils.usb.passthrough import is_usb_passthrough_enabled
      assert is_usb_passthrough_enabled()


ACL 設定
========

ACL 預設為 ``"deny"``\ ，所以 viewer 無法 claim 操作員未核准的裝置。
新增 per-device rule：

1. 從 GUI — host 的 *USB* 分頁在第一次 OPEN 未知裝置時會跳出 prompt
   對話框。勾 *記住這個決定* 把永久 allow rule 寫入。
2. 從 Python::

      from je_auto_control.utils.usb.passthrough import (
          AclRule, UsbAcl,
      )
      acl = UsbAcl()
      acl.add_rule(AclRule(
          vendor_id="1050", product_id="0407",
          serial=None,            # match 任何 serial
          label="YubiKey 5",
          allow=True,
          prompt_on_open=False,   # 一旦核准就靜默 allow
      ))

3. 直接編輯 ``~/.je_auto_control/usb_acl.json``\ 。檔案有權限檢查
   （POSIX 上 mode ``0600``\ ）。壞 JSON 或未知 ``version`` 會退到
   預設 deny。

決策優先序：

- 第一個 match 的 rule 勝。``prompt_on_open=True`` 表示每次都重問
  操作員，即使 rule 是 ``allow=True``\ 。
- 沒有 rule match 時套用檔案的 ``default``\ （預設 ``"deny"``\ ）。


啟動 host
=========

host 需要 REST API 在跑（這樣 viewer 才能列舉），加上一條對 viewer
的 WebRTC peer connection（這樣 transfer 才能流動）。

REST::

    from je_auto_control.utils.rest_api import start_rest_api_server
    server = start_rest_api_server(host="0.0.0.0", port=9939)
    print("Bearer:", server.token)

WebRTC：用既有的遠端桌面流程（見 :doc:`operations_layer_doc`\ ）建立
session。viewer 端的 ``UsbPassthroughClient`` 之後就接到談妥的
DataChannel 上。


Viewer 端：claim 與 transfer
============================

列舉
----

從 Python::

    import urllib.request, json
    req = urllib.request.Request(
        "http://host:9939/usb/devices",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.loads(r.read())
    for d in body["devices"]:
        print(d["vendor_id"], d["product_id"], d.get("product"))

或用 viewer 端的 *USB Browser* GUI 分頁：貼上 host 的 REST URL +
token，按 *Fetch devices*\ 。

Open + transfer
---------------

::

    from je_auto_control.utils.usb.passthrough import (
        UsbPassthroughClient, encode_frame, decode_frame,
    )

    # `data_channel` 是你 WebRTC 上 "usb" channel 的 RTCDataChannel。
    def send(frame):
        data_channel.send(encode_frame(frame))

    client = UsbPassthroughClient(send_frame=send)
    # 接上 channel 的 on-message callback：
    data_channel.on("message")(lambda raw: client.feed_frame(decode_frame(raw)))

    handle = client.open(vendor_id="1050", product_id="0407")
    response = handle.control_transfer(
        bm_request_type=0xC0, b_request=6, w_value=0x0100, length=18,
    )
    print("device descriptor:", response.hex())
    handle.close()
    client.shutdown()

錯誤：

- ``UsbClientTimeout`` — host 超過 ``reply_timeout_s``\ （預設 10 秒）
  沒回。檢查網路 / host 程序。
- ``UsbClientError`` — host 回 ``{ok: false, error: ...}``\ 。最常見
  情境是 *denied by ACL policy* — 去看 host 端的 prompt 對話框或 ACL
  規則。
- ``UsbClientClosed`` — client 或其 handle 已 shutdown。


疑難排解對照表
==============

==========================================  =====================================================
症狀                                        可能原因／處理
==========================================  =====================================================
``open`` 回 ``denied by ACL policy``        沒有 allow rule 且 ``default = deny``\ 。加 rule
                                            或啟用 prompt callback。
``open`` 回 ``no device matches``           裝置沒被列舉。看 ``UsbHotplugWatcher`` 輸出或直接
                                            跑 ``list_usb_devices()``\ 。Windows 上確認 Zadig
                                            綁定。
transfer 上 ``credit exhausted``            viewer 送的 frame 超過 host ``initial_credits`` 的
                                            window。降低請求頻率或在 session 上提高
                                            ``initial_credits``\ 。
Transfer ``UsbClientTimeout``               host 程序忙或 WebRTC channel 壞了。看 *Packet
                                            Inspector* 分頁的 RTT / 封包遺失。
OPEN 後 host 鍵盤停止運作                   Linux：HID 裝置被 claim 且 ``usbhid`` 被 detach。
                                            CLOSE 時 driver 會重新 attach；如果沒有，用
                                            ``udevadm trigger`` 救回。
稽核鏈顯示 ``broken_at_id``                 有人直接編輯了 ``audit.db``\ 。從備份還原；調查。
==========================================  =====================================================


尚未發布的部分
==============

- WebRTC viewer GUI 沒有自動把 ``usb`` DataChannel 接起來 — *USB
  Browser* 分頁的 *Open* 按鈕會顯示「尚未串接」訊息。今天可以從
  Python 驅動協定。
- Windows WinUSB transfer 方法已寫但尚未對實體硬體驗證。請勿用於
  production。
- macOS IOKit backend 未實作（Phase 2c）。
- Phase 2e 外部安全審查尚未簽核；feature flag 必須維持顯式 opt-in。
