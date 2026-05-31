================================================
USB Passthrough — 第二階段設計
================================================

.. note::
   **軟體面已全部完成；八個未決問題全部拍板（見「設計決策」）。**
   剩餘兩項本質上無法靠寫程式完成：**真實 USB 硬體驗證** 與
   **外部人員的安全 sign-off（Phase 2e）**。在這兩項完成前，
   feature flag 維持預設 off。

   **已完成並發布（rounds 27 / 34 / 37 / 39 / 40 / 41 / 42 / 43）：**
   Phase 1（唯讀列舉）、Phase 1.5（hotplug events）、Phase 2a
   （協定 + ABC + ``LibusbBackend`` lifecycle + 給測試用的
   ``FakeUsbBackend`` + feature flag，預設 off）、Phase 2a.1
   （完整 ``LibusbBackend`` 傳輸 + CREDIT-based 入站流量控制 +
   稽核 hook）、**viewer 端 ``UsbPassthroughClient``**\ （阻塞式
   open / control_transfer / bulk_transfer / interrupt_transfer / close /
   list_devices，含 outbound credit 等待與 shutdown 傳播）、Phase 2d
   （``UsbAcl`` 持久化白名單、ACL-gated OPEN 含 prompt-callback、
   稽核紀錄整合到既有的 tamper-evident 鏈）、Phase 2d.1
   （ACL 檔案 HMAC-SHA256 完整性，竄改則 fail-closed）。

   **Phase 2b — Windows ``WinUSB``：** SetupAPI 列舉 + ``WinUsb_*``
   傳輸的 ctypes 接線已完成（**硬體未驗證**）。

   **Phase 2c — macOS ``IOKit``：** 透過 ctypes 的原生 IOKit 列舉已
   完成；裝置 claim／傳輸委派給 libusb（macOS 上經硬體驗證的路徑）。
   詳見 ``iokit_backend`` 模組說明（**硬體未驗證**）。

   **backend 選擇：** ``default_passthrough_backend()`` 依 OS 自動挑
   WinUSB / IOKit / libusb。

   **剩餘流程：** Phase 2e — 見 :doc:`usb_passthrough_security_review`
   的審查者清單；feature flag 翻成預設 on 之前必須由外部人員簽核，
   且三個 backend 都需在真實硬體上跑過測試矩陣。

.. contents::
   :local:
   :depth: 2


目標
====

讓遠端 AutoControl viewer 使用實體插在 host 機器上的 USB 裝置。
具體使用情境：

- 在 host 插一支 USB security key；讓 viewer 發起的 WebAuthn
  challenge 在那支 key 上簽章。
- 在實驗室 host 插 USB-serial debug board；讓遠端開發者透過自己
  本機的終端機跟它對話。
- 在 host 插一台印表機；讓 viewer 的 OS 把它看成本機印表機。

非目標
======

- **高吞吐 isochronous 傳輸**\ （USB webcam、音訊介面）。WebRTC +
  DataChannel + driver 來回的延遲預算跟 isochronous USB 不相容。
  那些情境用既有的 audio/video track。
- **核心層裝置重導向**\ （如 USB/IP）。我們做的是 userspace
  forwarder，不是替代 kernel driver。
- **第二階段在通過明確的安全審查之前不會發布。**


傳輸
====

Channel
-------

每個 session 一條專用的 WebRTC ``DataChannel``\ ，名稱 ``usb``\ ，
``ordered=True`` 且 ``maxRetransmits=None``\ （完全可靠傳輸）。
USB 的 bulk 與 interrupt 傳輸對延遲的容忍度遠高於對遺失的容忍度；
既有的 video/audio channel 也已示範底層 SCTP 傳輸足以承擔有序可靠
串流。

**已決（OQ1）：** 維持 ``ordered=True`` + ``maxRetransmits=None``
（完全可靠有序）。USB control 傳輸（如 WebAuthn 簽章、descriptor
讀取）對遺失零容忍，部分遺失的串流會讓裝置狀態機壞掉；可靠有序的
語意比節省幾毫秒重傳延遲重要。``maxPacketLifeTime`` 的有界遺失模型
留給未來若出現純高吞吐、可容忍遺失的使用情境再評估（目前 YAGNI）。

Framing
-------

每個 channel message 是一個前綴長度的協定 frame::

    +-----+--------+----------+--------------------+
    | 1B  |   1B   |    2B    |       payload      |
    | op  | flags  | claim_id | (op-specific body) |
    +-----+--------+----------+--------------------+

- ``op``：1 byte opcode（見下方 *操作*）
- ``flags``：8 bits，目前只用到 ``EOF``\ （bit 0，分塊讀取用）
- ``claim_id``：16-bit 識別碼，代表單一 session 中的一次 device
  claim。host 在 OPEN 時配發、在 CLOSE 時回收。
- payload：依 opcode 不同。上限 16 KiB 以維持 DataChannel 訊息
  尺寸合理。

**已決（OQ2）：** 已實作分片。``protocol.fragment_payload()`` 把超過
16 KiB 的 payload 切成多個同 ``claim_id`` 的 frame，除最後一個外都清掉
``FLAG_EOF``；接收端串接連續 frame 的 payload 直到看到 EOF。傳輸回覆
與 ``LIST`` 回覆都走這條路；single-frame 的常見情形仍只送一個帶 EOF
的 frame，行為與先前一致。

操作
----

================  =====================================  ======================
Op (hex)          方向                                   用途
================  =====================================  ======================
``0x01 LIST``     viewer → host、host → viewer（回應）   列舉 viewer 有權 claim 的裝置
``0x02 OPEN``     viewer → host                          請求 claim (vendor_id, product_id, serial)
``0x03 OPENED``   host → viewer                          回覆：成功 + claim_id，或錯誤
``0x04 CTRL``     viewer ↔ host                          Control 傳輸（bmRequestType, bRequest, wValue, wIndex, data）
``0x05 BULK``     viewer ↔ host                          指定 endpoint 的 Bulk IN/OUT 傳輸
``0x06 INT``      viewer ↔ host                          Interrupt IN/OUT 傳輸
``0x07 CREDIT``   viewer ↔ host                          Backpressure 視窗更新
``0x08 CLOSE``    viewer → host                          釋放 claim
``0x09 CLOSED``   host → viewer                          確認（host 端斷線時也可主動發出）
``0xFF ERROR``    雙向                                   協定錯誤／不支援 op
================  =====================================  ======================

**已決（OQ3）：** ``LIST`` 走 channel。``session`` 處理 ``LIST`` frame
並回傳 ACL 不會 deny 的裝置（被 deny 的裝置連存在都不讓 viewer 知道）；
viewer 端用 ``UsbPassthroughClient.list_devices()`` 取得。讓列舉與傳輸
共用同一條已通過 auth gate 的 channel，避免再耦合一層 REST transport，
也讓 ACL 過濾與 claim 決策走同一份邏輯。

Backpressure
-------------

雙方各以 16 個未確認 frame 為 ``claim_id`` 的初始 credit window。
收一個 frame 消一個 credit；用 ``CREDIT`` 訊息傳正整數來補回。
沒有流量控制的話，慢的遠端 USB 裝置會把 DataChannel 送出 buffer
撐爆。

**已決（OQ4）：** 維持 per-claim credit。它已足以達成核心目的——
防止慢速遠端裝置撐爆 host 送出 buffer——而且狀態最少、推理最簡單。
per-endpoint credit 會把 IN/OUT、多 bulk endpoint 各自記帳，複雜度
明顯上升卻只在單一 claim 內多個 endpoint 同時飽和時才有差別；屬於
YAGNI，待真實量測出現 head-of-line 問題再說。


各 OS driver 包裝
==================

driver 層藏在單一 ``UsbBackend`` ABC 後面::

    class UsbBackend(abc.ABC):
        def open(self, vendor_id, product_id, serial) -> "UsbHandle": ...
        def list(self) -> list[UsbDevice]: ...

    class UsbHandle(abc.ABC):
        def control_transfer(self, ...): ...
        def bulk_transfer(self, endpoint, data, timeout_ms): ...
        def interrupt_transfer(self, endpoint, data, timeout_ms): ...
        def close(self): ...

這把 OS 特定的東西隔離開，讓我們可以在不選定 backend 的前提下
寫協定／session 層。

Windows — WinUSB
----------------

- 對於我們沒有現成 driver 的 HID-class 裝置，最佳路徑：用 libwdi
  安裝 ``WinUSB``，或讓使用者透過 Zadig 手動把裝置綁到 WinUSB。
- 用 ``CreateFile`` + ``WinUsb_Initialize`` + ``WinUsb_ControlTransfer``
  ／``WinUsb_ReadPipe``／``WinUsb_WritePipe``。
- ``ctypes`` 包 ``winusb.dll`` 的 wrapper 是 public API；不需要
  寫 kernel driver。

**已決（OQ5）：** WinUSB 要求裝置 *尚未被別的 driver claim*，且只有
已綁定 ``winusb.sys`` 的裝置會出現在 ``WinusbBackend.list()`` 中。因此
host OS 自己擁有的裝置（印表機、hub、鍵盤）根本不會列出來——viewer
看到的就是「可 claim」的子集，不會誤以為能 claim 系統裝置。若 OPEN
的 vid/pid 不在清單中，host 回明確的 ``no device matches`` 錯誤；
operator guide 說明如何用 Zadig / libwdi 綁定裝置到 WinUSB。

macOS — IOKit
-------------

- ``IOUSBHostInterface``\ （現代版，10.12 起）或 ``IOUSBInterfaceInterface``
  （比較舊但無所不在），透過 ``pyobjc``。
- 透過 App Store 發行需要 entitlement 簽章；直接散布的話 OK，但
  binary 必須做 notarisation。
- IOKit 的 ``CompletionMethod`` callback 整合 ``CFRunLoop``，不是
  asyncio。需要一個專屬 thread 持有 runloop，把 completion marshal
  回 WebRTC bridge thread。

**已決（OQ6）：** 列舉走原生 IOKit（ctypes，不需 pyobjc）；claim／
傳輸委派給 libusb——它是 macOS 上經硬體驗證的 USB 路徑，避免手刻
無法在無硬體下驗證的 ``IOUSBHostInterface`` plugin vtable。直接散布
（非 App Store）的 build 必須 notarisation；libusb 存取裝置不需特殊
entitlement，但 System Integrity Protection 仍會藏起 Apple 內部裝置與
某些 USB-C 週邊。operator guide 記載 SIP 排除界線。

Linux — libusb
--------------

- 透過 ``libusb-1.0`` 的 ``pyusb`` 不需要 root，只要 ``udev``
  rule 給使用者存取權。我們會提供範例 rule。
- 拔線處理：libusb 對進行中的傳輸發出 ``LIBUSB_TRANSFER_NO_DEVICE``；
  我們把它 map 成 channel 上的 ``CLOSED``。

**已決（OQ7）：** 已實作。``_LibusbHandle`` 在 open 時對 active
configuration 的每個介面呼叫 ``detach_kernel_driver``（只 detach 真的
被 kernel 佔住的），記住動過哪些介面，並在 close 時 ``attach_kernel_driver``
復原——否則 session 結束後 host OS 會永久丟掉鍵盤／滑鼠。Windows／
macOS 的 libusb 對 detach 拋 ``NotImplementedError``，會被容忍跳過
（那些平台由 OS 仲裁 driver）。


安全與 ACL
==========

每裝置白名單
-------------

存於 ``~/.je_auto_control/usb_acl.json``::

    {
      "version": 1,
      "rules": [
        {"vendor_id": "1050", "product_id": "0407", "label": "YubiKey 5",
         "allow": true, "prompt_on_open": true},
        ...
      ],
      "default": "deny"
    }

- 預設政策是 **deny**。使用者沒有明確允許過的裝置不能被 claim。
- ``prompt_on_open`` 在每次 viewer 請求 OPEN 時觸發 host 端 modal。
  modal 顯示 vendor/product/serial 與請求存取的 viewer ID。
- Allow rule 可以靠提示中的「記住」勾選持久化。

**已決（OQ8）：** 已實作 HMAC-SHA256。ACL 旁附一個 ``<acl>.sig``
sidecar 簽章；載入時驗證，不符就 fail-closed（default-deny、
``integrity_ok`` 為 False），讓偷偷改寫 JSON 的 process 無法在不同時
偽造簽章的情況下給自己授權。簽章金鑰可插拔——部署可透過建構子的
``hmac_key=`` 傳入由平台 keychain 衍生的金鑰；未指定時會在 ACL 旁
產生一把隨機金鑰檔（POSIX 上 ``0o600``）。注意：同使用者身分的
process 仍可讀金鑰檔而偽造簽章，故高保證部署建議改用 keychain 金鑰
（見 operator guide）。升級前既有的未簽章檔案視為 legacy，仍可載入
（下次儲存即補簽），可用 ``require_signature=True`` 拒絕未簽章檔。

稽核
----

每筆 OPEN、OPENED、CLOSE、ERROR 都附加到既有稽核紀錄，event_type
``"usb_passthrough"``。Frame 層傳輸紀錄太雜，只在 ERROR 時記錄。

權限
----

host process 必須以選定 backend 所需的權限執行（Linux udev rule、
macOS entitlement、Windows WinUSB 通常不需要）。README 會逐 OS
寫清楚。


階段
====

1. **完成 — Phase 1**：唯讀列舉（``list_usb_devices``）。
2. **完成 — Phase 1.5**：hotplug events（``UsbHotplugWatcher``、
   ``/usb/events``）。
3. **完成 — Phase 2a**：協定 + ``UsbBackend`` ABC + Linux
   ``libusb`` backend，置於 feature flag 之後。
4. **完成 — Phase 2b**：Windows ``WinUSB`` backend（ctypes，硬體未驗證）。
5. **完成 — Phase 2c**：macOS ``IOKit`` backend（原生列舉 + libusb
   傳輸，硬體未驗證）。
6. **完成 — Phase 2d / 2d.1**：ACL 持久化 + host 端提示 callback +
   稽核整合 + ACL 檔案 HMAC 完整性。
7. **進行中 — Phase 2e**：默認開啟之前的外部安全審查 **加上** 三個
   backend 的真實硬體測試矩陣。這兩項本質上需要硬體與外部人員，
   無法只靠程式碼完成。

在 Phase 2e 簽核之前，feature flag 維持預設 off。


設計決策（原未決問題）
======================

八個原始未決問題均已拍板，對應實作見上方各節：

1. **OQ1 — Channel 可靠度**：``maxRetransmits=None``（完全可靠有序）。
2. **OQ2 — frame 分片**：已實作 ``fragment_payload`` + EOF 重組。
3. **OQ3 — ``LIST`` 走 channel**：是，ACL 過濾後經 channel 回傳。
4. **OQ4 — Backpressure 顆粒度**：per-claim（per-endpoint 屬 YAGNI）。
5. **OQ5 — WinUSB 不可 claim 裝置**：只列出已綁 WinUSB 的裝置，
   claim 不到回明確錯誤。
6. **OQ6 — macOS 發行**：原生 IOKit 列舉 + libusb 傳輸；notarisation，
   無需特殊 entitlement，文件記載 SIP 界線。
7. **OQ7 — Linux kernel driver**：open 時 detach、close 時 reattach。
8. **OQ8 — ACL 完整性**：HMAC-SHA256 sidecar，金鑰可插拔（keychain）。
