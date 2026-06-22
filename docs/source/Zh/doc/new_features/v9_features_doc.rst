========================================
新功能 (2026-06-19) — 無人值守可靠性
========================================

三個針對無人值守與登入自動化的社群痛點修復:產生 2FA 驗證碼、操作原生
檔案對話框、以及拒絕在鎖定畫面上動作。每項都走完整五層(facade、
``AC_*`` 執行器指令、MCP 工具、Script Builder),且完全 headless——外部
步驟皆為決定性或可注入,因此不需 2FA、真實對話框或鎖定工作階段即可單元
測試。

.. contents::
   :local:
   :depth: 2


2FA 登入的 OTP / TOTP
=====================

2FA 會擋住自動登入。把 base32 secret 存好(最好放進 secrets store),在
流程中即時產生當前驗證碼::

    from je_auto_control import generate_totp, verify_totp

    code = generate_totp(secret)          # 當下的 6 碼 TOTP
    type_text(code)

``AC_otp_to_var`` 會把驗證碼寫進流程變數供下一步使用::

    ["AC_otp_to_var", {"secret": "JBSWY3DPEHPK3PXP", "var": "otp"}]
    ["AC_type_keyboard", {"keycode": "${otp}"}]

重用支撐遠端桌面驗證的 TOTP 引擎。執行器指令:``AC_otp_to_var``;
MCP 工具:``ac_generate_otp``。


原生檔案對話框
==============

錄製器抓不到 OS 的檔案開啟/儲存/資料夾對話框,大家只好手刻「輸入路徑 +
Enter」。``handle_file_dialog`` 一次搞定::

    from je_auto_control import handle_file_dialog

    handle_file_dialog("C:/reports/out.csv", action="save")

``action`` 為 ``open`` / ``save`` / ``folder``(自動選預設對話框標題),
或傳明確的 ``window_title``;它會等對話框、輸入路徑、按 ``confirm_key``
(預設 Enter)。等視窗/輸入/確認三步透過可注入的 :class:`FileDialogDriver`。
執行器指令:``AC_handle_file_dialog``。


鎖定工作階段守衛
================

無人值守在工作站鎖定或 RDP 斷線時會默默失敗——輸入會 no-op 或拋例外。
先檢查::

    from je_auto_control import ensure_interactive_session, is_session_locked

    ensure_interactive_session()          # 鎖定時拋例外
    if is_session_locked():
        ...

Windows 上以開啟 input desktop 偵測(鎖定時會失敗);其他平台除非提供自訂
probe,否則回報「未鎖定」。執行器指令:``AC_assert_session_active``——放在
無人值守腳本最前面,讓它清楚地失敗,而非送出幽靈點擊。
