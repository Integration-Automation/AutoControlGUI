權杖預算化的觀測差異(變更了什麼)
====================================

``observation.serialize_observation`` 渲染*單一整幀*的 UI——每回合都餵給模型會撐爆該模組
原本就要節省的權杖預算,並迫使模型為了發現那一個新對話框而重讀整個畫面。``element_diff``
提供兩幀之間的穩定 ID 對應,但止於 matched / added / removed 的*元素配對*——它不會渲染出
模型可據以行動的精簡、帶索引、受預算限制的差異。

``observation_delta`` 正是缺少的序列化器:它比對前一幀與當前觀測,將每個配對元素分類為
*changed*(role / name / enabled / value / 移動)或 *stable*,並只渲染變動部分——
``+ [i] role "name"``(出現)/ ``- role "name"``(消失)/ ``~ [i] role "name" (fields)``
(變更)——added 與 changed 優先、stable 略去、上限為 ``max_lines``。模型看到的是*變更了什麼*,
而非再次整個畫面。

純標準函式庫,作用於元素字典;重用 ``element_diff.match_elements`` 做重疊配對、
``observation.observation_index`` 做閱讀順序索引。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import delta_observation, delta_index, summarize_delta

    summary = delta_observation(prev_elements, curr_elements, max_lines=40)
    # + [12] dialog "Saved"
    # ~ [4] button "Submit" (enabled)
    # - button "Spinner"

    delta = delta_index(prev_elements, curr_elements)   # {added, removed, changed, stable}
    text = summarize_delta(delta, max_lines=20)

``delta_index`` 回傳 ``{added, removed, changed, stable}``(``changed`` 項目為
``{"after", "fields"}``);``summarize_delta`` 把 ``delta_index`` 結果渲染為受預算限制的
``+`` / ``~`` / ``-`` 行;``delta_observation`` 將兩幀索引化(閱讀順序、視口裁切、僅互動元素)
後再比對並渲染,一次完成。

執行器指令
----------

``AC_delta_observation``(``prev`` / ``curr`` / ``viewport`` / ``max_elements`` / ``max_lines``
/ ``interactive_only`` → ``{summary, added, removed, changed}``)以 MCP 工具
``ac_delta_observation``(唯讀)及 Script Builder 指令 **Observation: Delta (what changed)**
(位於 **Native UI** 分類下)形式提供。
