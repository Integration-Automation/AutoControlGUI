================================================
USB Passthrough — Phase 2e 安全審查清單
================================================

本頁是給外部審查者在 USB passthrough 預設啟用之前要走過一遍的清單。
**它本身不是 sign-off** — 簽核紀錄留在專案使用的 ticket / 紀錄系統。

在以下每一項都被一個 *非程式作者* 的審查者 check 並簽核之前，
passthrough 必須留在 ``enable_usb_passthrough(True)``\ （預設 off）
之後。

.. contents::
   :local:
   :depth: 2


威脅模型
========

信任邊界：**viewer** 是 host 本機信任域之外的 peer。他們可以在
``usb`` DataChannel 上送任意 frame。host 絕對不可：

- claim 操作者沒有授權的裝置（ACL）。
- claim 超過政策上限的裝置數量（max_claims）。
- 在 viewer 驅動的 payload 上花無上界的 buffer 空間（payload cap +
  credit window）。
- 對明確行為不端的 viewer 繼續服務（rate / lockout，channel 與同
  session 共用 REST auth gate 時繼承）。

viewer 也可能是惡意 host 的受害者 — 但本清單只涵蓋 host 端。
viewer client 的審查獨立排在 Phase 2f。


ACL
===

- [ ] 沒有檔案時，``UsbAcl`` 預設為 ``"deny"``。用全新使用者帳號驗證。
- [ ] 檔案損毀／版本不對時，ACL 同樣預設 deny（測試
      ``test_unknown_version_is_ignored``\ ）。
- [ ] ``prompt_on_open`` rule 沒接 callback 時退到 deny（測試
      ``test_session_prompt_no_callback_means_deny``\ ）。
- [ ] prompt callback 拋例外時，open 視為被拒（測試
      ``test_session_prompt_callback_raising_means_deny``\ ）。
- [ ] ACL 檔案在 POSIX 上以 mode ``0o600`` 寫入（測試
      ``test_save_persists_to_disk_with_safe_mode``\ ）。
- [ ] 建議把 ACL 放在支援 POSIX 權限的檔案系統上；佈署文件需把
      Windows ACL 故事寫清楚。
- [ ] **OQ8 — ACL 完整性（HMAC）已實作**\ 。ACL 旁附 HMAC-SHA256
      sidecar 簽章，竄改則 fail-closed（測試
      ``test_tampered_acl_file_fails_closed``\ 、
      ``test_explicit_key_roundtrip_and_wrong_key_fails``\ ）。**殘留風險：**
      預設金鑰存於同使用者可讀的 ``usb_acl.json.key``\ ；同身分的
      process 仍可偽造簽章。高保證部署應透過 ``UsbAcl(hmac_key=...)``
      改用平台 keychain 衍生金鑰——請審查者確認部署是否採用。


稽核
====

- [ ] 每個 ACL 決策都透過 ``audit_log`` 以下列其中一個 event_type 記錄：
      ``usb_open_allowed``、``usb_open_denied``、
      ``usb_open_rejected_max_claims``、``usb_open_backend_error``、
      ``usb_close``\ 。手動跑一次後檢視最近的稽核行確認。
- [ ] 稽核行帶 ``viewer_id``，可追溯到特定 peer（測試
      ``test_session_audit_captures_open_decisions``\ ）。
- [ ] 稽核紀錄本身有雜湊鏈（round 25）。Passthrough session 結束後
      確認 ``verify_chain()`` 回 ``ok=True``\ 。
- [ ] frame 層傳輸紀錄刻意 **不** 開，避免擷取 YubiKey 之類裝置的
      key material。只有 ERROR 透過專案 logger 顯示。


協定強化
========

- [ ] Frame header 4 bytes；``decode_frame`` 拒絕短於這個的 buffer
      （測試 ``test_decode_rejects_short_buffer``\ ）。
- [ ] 未知 opcode 拋 ``ProtocolError``\ （測試
      ``test_decode_rejects_unknown_opcode``\ ）— session 不會看到壞 frame。
- [ ] Payload 上限 ``MAX_PAYLOAD_BYTES``\ （16 KiB），decode（測試
      ``test_decode_rejects_oversize_payload``\ ）與 construct（測試
      ``test_frame_constructor_validates``\ ）兩端都檢查。
- [ ] CTRL/BULK/INT request body 解析失敗回 ERROR，不 crash（測試
      ``test_bad_transfer_payload_returns_error``\ ）。
- [ ] backend 例外 catch 後翻成 ``{ok: false, error: ...}`` — session
      絕不把 host 端 RuntimeError 傳到 wire（測試
      ``test_backend_error_translates_to_ok_false``\ ）。


資源上界
========

- [ ] ``max_claims`` 上限有效（測試
      ``test_max_concurrent_claims_enforced``\ ）。
- [ ] CREDIT-based 入站流量控制阻止 peer 灌滿 host process queue
      （測試 ``test_credit_exhaustion_returns_error``\ ）。
- [ ] CREDIT 補充每個 reply 1 個 — well-behaved peer 不會 stall
      （測試 ``test_each_transfer_consumes_then_replenishes_one_credit``\ ）。
- [ ] 壞 payload 的 CREDIT 訊息靜默丟掉（測試
      ``test_credit_message_with_bad_payload_is_ignored``\ ）。
- [ ] 未知 claim_id 的 CREDIT 靜默（測試
      ``test_credit_message_for_unknown_claim_is_silent``\ ）。


生命週期
========

- [ ] ``close_all()`` 釋放每個未結 handle，且容忍 per-handle close
      錯誤（測試 ``test_close_all_releases_every_outstanding_claim``\ ）。
- [ ] FakeHandle ``close`` 是 idempotent（測試
      ``test_backend_handle_close_is_idempotent``\ ）；libusb backend
      在硬體測試時驗證同樣性質。
- [ ] 關閉 handle 之後再發 transfer 會 raise（測試
      ``test_fake_handle_transfer_after_close_raises``\ ）。
- [ ] viewer client ``shutdown()`` 釋放任何等待中的 request waiter
      （測試 ``test_shutdown_unblocks_pending_transfers``\ ）。


各 OS 需求
==========

- [ ] **Linux libusb**：目標裝置的 udev rule 文件化；非 root 測試。
- [ ] **Linux libusb**：HID 裝置 claim 之前呼叫
      ``libusb_detach_kernel_driver``\ ；close 時重新 attach。
      確認 host OS 的鍵盤／滑鼠在 session 結束後仍可運作。
- [ ] **Windows WinUSB**\ （Phase 2b — *已實作，硬體未驗證*）：裝置
      必須已與 WinUSB 關聯（Zadig / libwdi），只有綁定者會出現在
      ``list()``\ 。在真實硬體上跑 bulk / HID / composite 測試矩陣後
      才能簽核。
- [ ] **macOS IOKit**\ （Phase 2c — *已實作，硬體未驗證*）：原生 IOKit
      列舉 + libusb 傳輸。非 App Store 發行需 notarisation；文件化 SIP
      排除清單。在真實硬體上跑測試矩陣後才能簽核。
- [ ] 三個 backend 都要：開啟已被別 driver 持有的裝置時，要清楚地
      回 "busy" RuntimeError，不 hang 不 crash。


滲透測試情境
============

以下是建議外部 pen-tester 在 sign-off 之前嘗試的情境。**沒有一項
應該成功**\ ：

1. **ACL 大小寫繞過**\ 。試試混合大小寫與前置零的 VID/PID；確認
   只有正規形式會 match。
2. **Unicode 正規化繞過**\ 。試試視覺相同但 Unicode 不同的序號
   字串。
3. **Credit DoS**\ 。在小 ``max_claims`` 之下盡可能快速送 100 萬筆
   transfer frame；確認 host RSS 維持上界。
4. **Frame 切片攻擊**\ 。送 header 宣稱 payload 比實際抵達大的 frame；
   確認 ``decode_frame`` 拒絕被截斷的 stream。
5. **並行 OPEN race**\ 。兩個 peer（或一個 peer 多 thread）同時 OPEN
   — 確認每個 OPEN request 剛好得到一個 ``claim_id``、bookkeeping
   不漂移。
6. **稽核竄改**\ 。直接用 raw SQLite 編輯 ``audit.db`` 中的某個
   ``usb_*`` row；確認 ``verify_chain()`` 會 flag 出來。
7. **Prompt callback 計時**\ 。慢的 prompt callback（sleep 30 秒）
   不應允許另一個 peer 趁機塞 CTRL — 確認 prompt callback 完成前
   同一 vid/pid 的後續決策都會等待。
8. **權限 downgrade**\ 。在 Linux 以非特權使用者跑 host 而沒有 udev
   rule；確認 OPEN 乾淨地失敗，回清楚的 "permission denied" 訊息
   而非 crash。


Sign-off
========

審查者姓名：__________________________________________________

審查者單位：__________________________________________________

日期：________________________________________________________

以上項目全部 check：[ ] 是  [ ] 否 — 在下方列未通過項目。

建議：

  [ ] 可以發布 Phase 2 預設啟用。
  [ ] 可以發布但保持目前的 opt-in flag。
  [ ] block 釋出；需要 remediation。

備註／remediation 清單：
