可讀性評分
==========

文字工具能正規化(``text_normalize``)、比對(``text_similarity``、``fuzzy``)與排名(``search_index``)文字,
但沒有任何功能能評估文字*有多難讀*。先前無法斷言畫面訊息、產生的標籤或文件字串是否落在目標閱讀年級內。
本功能在決定性的斷詞器與音節啟發式之上,加入經典的英文可讀性公式。

純標準函式庫(``re`` / ``math``);不匯入 ``PySide6``。每個函式皆為純函式(文字進、數字/報告出),因此在 CI 中
完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        flesch_reading_ease, flesch_kincaid_grade, gunning_fog, smog_index,
        automated_readability_index, readability_report, readability_stats,
        count_syllables,
    )

    flesch_reading_ease("The cat sat on the mat.")     # ~116(非常易讀)
    flesch_kincaid_grade(marketing_copy)               # 美國年級
    readability_report(text)                           # 所有指標 + 計數

    # 以閱讀年級把關產生的 UI 文案
    assert flesch_kincaid_grade(label) <= 8

``readability_stats`` 回傳每個公式共用的原始計數(``words``、``sentences``、``syllables``、``characters``、
``complex_words``)。``flesch_reading_ease`` 為愈高愈易讀(一般文章約 0-100);其餘(Flesch-Kincaid、
Gunning Fog、SMOG、ARI)回傳美國年級。``count_syllables`` 是公式所依據的啟發式母音群計數器(含無聲 ``e`` 與
子音 + ``le`` 處理)。``readability_report`` 將五個指標連同計數打包成一個 dict。

執行器命令
----------

``AC_readability_report`` 對單一字串回傳完整報告(五個指標加計數)。它以 MCP 工具 ``ac_readability_report``
以及 Script Builder 中 **Data** 分類下的命令提供。
