讀取與控制系統音量
==================

無人值守的執行常需要一個已知的音訊基準——在吵雜的批次前靜音、結束後還原音量,或斷言目前音量——但框架
原本只有盲目的媒體鍵步驟(``volume up`` / ``down`` 以未知幅度推移,且無法讀回)。``system_volume``
補上對預設輸出裝置的絕對、可讀回控制。

* :func:`get_volume` / :func:`set_volume` / :func:`change_volume` ——以整數百分比 ``0..100``
  讀寫主音量(``set_volume`` 與 ``change_volume`` 會夾到該範圍)。
* :func:`is_muted` / :func:`set_mute` / :func:`mute` / :func:`unmute` /
  :func:`toggle_mute` ——讀寫靜音旗標。

所有邏輯(夾值、百分比 <-> 純量轉換、切換)皆為純函式,並透過可注入的 :class:`VolumeDriver` 接縫執行,
故能在不需音訊裝置的情況下完整測試。預設 driver 透過選用相依套件 ``pycaw``
(``pip install je_auto_control[audio]``)驅動 Windows Core Audio 的
``IAudioEndpointVolume`` 介面;在沒有該套件 / 非 Windows 平台上,預設 driver 會丟出清楚的錯誤,
提示呼叫端傳入 ``driver=``。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        get_volume, set_volume, change_volume, is_muted, mute, unmute,
        toggle_mute,
    )

    get_volume()            # 例如 65 ——目前主音量百分比
    set_volume(30)          # 設為 30 %,回傳 30
    change_volume(-10)      # 降低 10 %,回傳套用後的百分比
    is_muted()              # False
    mute()                  # True  ——使輸出靜音
    unmute()                # False ——還原
    toggle_mute()           # 切換並回傳新狀態

測試時(或任何非 Windows 主機)可傳入 ``driver`` ——任何以 ``0.0..1.0`` 純量提供
``get_scalar`` / ``set_scalar`` / ``get_mute`` / ``set_mute`` 的物件:

.. code-block:: python

    class FakeVolume:
        def __init__(self, scalar=0.5, muted=False):
            self.scalar, self.muted = scalar, muted
        def get_scalar(self): return self.scalar
        def set_scalar(self, s): self.scalar = s
        def get_mute(self): return self.muted
        def set_mute(self, m): self.muted = m

    drv = FakeVolume()
    set_volume(73, driver=drv)   # 73,drv.scalar == 0.73

執行器指令
----------

``AC_get_volume``(→ ``{volume, muted}``)、``AC_set_volume``(``level`` →
``{volume}``)、``AC_change_volume``(``delta`` → ``{volume}``)、``AC_set_mute``
(``muted`` → ``{muted}``)與 ``AC_toggle_mute``(→ ``{muted}``)。皆以對應的 ``ac_*``
MCP 工具(讀取為唯讀、寫入為僅副作用)及 Script Builder 指令(位於 **Shell** 分類下)形式提供。
執行器與 MCP 層使用預設 OS driver,故在 Windows 上需要 ``pycaw``。
