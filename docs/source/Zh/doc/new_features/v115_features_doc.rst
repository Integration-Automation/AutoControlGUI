檢查碼演算法
============

``pii_text`` 以正則偵測信用卡與 IBAN 的*形狀*、``data_quality`` 做型別/範圍/正則驗證,但沒有任何功能實際
計算或驗證*檢查碼*。本功能加入多數真實世界識別碼背後四種方案的共用運算引擎——也是帳號、卡號、IBAN、
ISBN、EAN 驗證所依據的基本元件。

純標準函式庫(整數運算;Verhoeff 與 Damm 表為小型內嵌常數)。每個函式皆為純函式(字串進、bool/str 出),
因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        luhn_validate, luhn_check_digit,
        verhoeff_validate, verhoeff_check_digit,
        damm_validate, damm_check_digit,
        mod97_10_validate, mod97_10_check_digits,
    )

    luhn_validate("4111111111111111")    # True  (信用卡 / IMEI)
    luhn_check_digit("7992739871")        # '3'   -> 79927398713
    verhoeff_validate("2363")             # True  (可抓出換位錯誤)
    damm_check_digit("572")               # '4'
    mod97_10_validate("3214282912345698765432161182")   # True  (IBAN 引擎)

- **Luhn**(mod 10):信用卡、IMEI、多種國民身分碼——可抓出所有單一數字錯誤與多數相鄰換位。
- **Verhoeff** 與 **Damm**:十進位方案,可抓出*所有*單一數字與相鄰換位錯誤(比 Luhn 更強)。
- **ISO 7064 MOD 97-10**:IBAN 等使用的雙檢查碼方案。

每個方案提供 ``*_validate(number)``(含檢查碼的值是否驗證通過?)與 ``*_check_digit`` / ``*_check_digits``
(對裸負載應附加哪些檢查碼?)。非數字字元會被忽略,因此含空格/分組的輸入也適用。

執行器命令
----------

``AC_checksum_validate`` 接受 ``scheme``(``luhn`` / ``verhoeff`` / ``damm`` / ``mod97``)與 ``number`` 並回傳
``{valid}``;``AC_checksum_digit`` 對 ``partial`` 回傳 ``{check_digit}``。兩者皆以 MCP 工具
(``ac_checksum_validate`` / ``ac_checksum_digit``)以及 Script Builder 中 **Data** 分類下的命令提供。
