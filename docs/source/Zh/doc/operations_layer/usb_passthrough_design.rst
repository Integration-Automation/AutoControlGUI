================================================
USB Passthrough — 第二階段設計（DRAFT）
================================================

.. warning::
   **DRAFT — Linux-libusb 路徑完成；跨平台 backend 為結構骨架。**

   **已發布（rounds 27 / 34 / 37 / 39 / 40 / 41 / 42）：**
   Phase 1（唯讀列舉）、Phase 1.5（hotplug events）、Phase 2a
   （協定 + ABC + ``LibusbBackend`` lifecycle + 給測試用的
   ``FakeUsbBackend`` + feature flag，預設 off）、Phase 2a.1
   （完整 ``LibusbBackend`` 傳輸 + CREDIT-based 入站流量控制 +
   稽核 hook）、**viewer 端 ``UsbPassthroughClient``**\ （阻塞式
   open / control_transfer / bulk_transfer / interrupt_transfer / close
   含 outbound credit 等待與 shutdown 傳播）、Phase 2d
   （``UsbAcl`` 持久化白名單、ACL-gated OPEN 含 prompt-callback、
   稽核紀錄整合到既有的 tamper-evident 鏈）。

   **結構骨架：** ``WinusbBackend``\ （Phase 2b）與
   ``IokitBackend``\ （Phase 2c）— class 骨架 + 平台／相依驗證已就位；
   ``list`` 與 ``open`` 拋 ``NotImplementedError`` 並指向模組內
   TODO 清單。這兩者需要 ctypes / pyobjc 接線 **加上硬體測試** 才能
   真正運作。

   **流程步驟：** Phase 2e — 見 :doc:`usb_passthrough_security_review`
   的審查者清單；feature flag 翻成預設 on 之前必須簽核。

   未決問題在內文中以 ``OPEN`` 標示，方便 reviewer 集中。

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

OPEN：是否應改用 ``maxPacketLifeTime``，給寬鬆預算（~5 秒）？
出貨前在真實 WAN 連線上測量看看再決定。

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

OPEN：需要超過 16 KiB 的 fragmentation 嗎？多數 USB 傳輸都裝得下；
control 傳輸受裝置的 wMaxPacketSize 限制。後續 frame 用相同
``claim_id`` 加 continuation flag 是低成本的擴充。

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

OPEN：``LIST`` 該走 channel，還是讓 viewer 用既有 REST
``/usb/devices`` 端點而 channel 只負責傳輸？後者比較簡單但耦合
兩層 transport。

Backpressure
-------------

雙方各以 16 個未確認 frame 為 ``claim_id`` 的初始 credit window。
收一個 frame 消一個 credit；用 ``CREDIT`` 訊息傳正整數來補回。
沒有流量控制的話，慢的遠端 USB 裝置會把 DataChannel 送出 buffer
撐爆。

OPEN：credit 該按 endpoint（IN/OUT 各別）還是按 claim？bulk
endpoint 是獨立的，按 endpoint 比較貼近硬體，但需要更多狀態。


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

OPEN：WinUSB 要求裝置 *尚未被別的 driver claim*。這排除了 host OS
認為自己擁有的裝置（印表機、hub、鍵盤）。需要在 app 內顯示為何某
些裝置 claim 不到的提示。

macOS — IOKit
-------------

- ``IOUSBHostInterface``\ （現代版，10.12 起）或 ``IOUSBInterfaceInterface``
  （比較舊但無所不在），透過 ``pyobjc``。
- 透過 App Store 發行需要 entitlement 簽章；直接散布的話 OK，但
  binary 必須做 notarisation。
- IOKit 的 ``CompletionMethod`` callback 整合 ``CFRunLoop``，不是
  asyncio。需要一個專屬 thread 持有 runloop，把 completion marshal
  回 WebRTC bridge thread。

OPEN：System Integrity Protection 會擋 Apple 自家裝置與某些 USB-C
週邊。要清楚記載這個界線。

Linux — libusb
--------------

- 透過 ``libusb-1.0`` 的 ``pyusb`` 不需要 root，只要 ``udev``
  rule 給使用者存取權。我們會提供範例 rule。
- 拔線處理：libusb 對進行中的傳輸發出 ``LIBUSB_TRANSFER_NO_DEVICE``；
  我們把它 map 成 channel 上的 ``CLOSED``。

OPEN：某些 distro 預設會把 ``usbhid`` 接到看起來像 HID 的所有東西。
得呼叫 ``libusb_detach_kernel_driver``，並在 close 時
``libusb_attach_kernel_driver`` 復原 — 否則 host OS 會丟掉輸入裝置。


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

OPEN：要不要對 ACL 檔案做簽章或 HMAC，避免被入侵的 host process
偷偷給自己授權？應該要，用一把使用者通行碼或平台 keychain 衍生的
master key。

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
3. **Phase 2a（本設計）**：協定骨架 + ``UsbBackend`` ABC + Linux
   ``libusb`` backend，置於 feature flag 之後。
4. **Phase 2b**：Windows ``WinUSB`` backend。
5. **Phase 2c**：macOS ``IOKit`` backend。
6. **Phase 2d**：ACL 持久化 + host 端提示 UI + 稽核整合。
7. **Phase 2e**：默認開啟之前的外部安全審查。

每個子階段都是獨立的多輪專案。經驗豐富的貢獻者預估工作量：每個
backend 約 1 週、ACL/UI 約 1 週，加上依 reviewer 行程而定的安全
審查。


未決問題彙整
============

1. Channel 用 ``maxRetransmits=None`` 還是 ``maxPacketLifeTime``。
2. 16 KiB 以上的 frame 分片。
3. ``LIST`` 走 channel 還是只走 REST。
4. Backpressure 顆粒度（per-claim 還是 per-endpoint）。
5. WinUSB 不能 claim 哪些裝置、要怎麼跟 viewer 溝通。
6. macOS 非 App Store 發行的 entitlement 故事。
7. Linux kernel driver detach/reattach 生命週期。
8. ACL 檔案完整性（HMAC 還是平台 keychain）。
