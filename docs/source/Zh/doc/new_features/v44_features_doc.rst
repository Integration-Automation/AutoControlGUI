語音指令路由器
==============

``VoiceRouter`` 將語音觸發*片語*對應到 ``AC_*`` 動作清單:餵入一段已辨識語句的文字,它
就會執行最接近的已註冊指令 —— 免手動觸發自動化流程。片語比對重用本專案的模糊比對器,因
此即使辨識有雜訊,「save the file」仍會觸發 ``"save file"`` 指令。

語音轉文字刻意**不在範圍內且可注入**:路由器接受的是已辨識的*文字*。真實的麥克風/Vosk
辨識器以 ``recognizer`` 可呼叫物件傳入 :meth:`VoiceRouter.listen_once`,如此路由邏輯可
在無音訊、無任何語音相依的情況下完整單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import VoiceRouter

    router = VoiceRouter(threshold=0.7)
    router.register("save file", [["AC_hotkey", {"keys": ["ctrl", "s"]}]])
    router.register("close window", [["AC_close_window", {}]])

    router.dispatch("save the file")     # 模糊比對 -> 執行儲存動作

    # 搭配真實辨識器(任何回傳文字的可呼叫物件):
    def vosk_listen() -> str:
        ...                              # 擷取音訊、回傳逐字稿
    router.listen_once(vosk_listen)

``dispatch``(與 ``listen_once``)接受 ``runner`` 來執行動作清單 —— 預設為執行器;注入假
物件即可在不執行真實自動化下測試路由。``match`` 回傳達到或高於 ``threshold`` 的最佳
``VoiceCommand``(否則 ``None``);``register`` 會取代既有片語;``phrases`` / ``clear``
則用於檢視與重置。

執行器指令
----------

模組層級的預設路由器支撐 executor/MCP 介面:

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_voice_register``            將 ``phrase`` 對應到 ``actions`` 清單。
``AC_voice_dispatch``            執行最符合已辨識 ``text`` 的指令。
``AC_voice_list``                列出已註冊片語。
``AC_voice_clear``               移除所有已註冊指令。
================================ ===================================================

``actions`` 接受清單或 JSON 字串清單(因此視覺化建構器可用)。相同操作亦提供為 MCP 工具
(``ac_voice_register`` / ``ac_voice_dispatch`` / ``ac_voice_list`` /
``ac_voice_clear``),以及 Script Builder 中 **Agent** 分類下的指令。
