符記預算內的無障礙文字觀測
============================

``screen_state.describe_screen`` 回傳角色*數量*加上控制項標籤的平面清單——但沒有穩定的逐元素索引、沒有
``[12] button "Submit" @(x,y)`` 行、沒有視口裁切,也沒有元素上限 / 符記預算。現代桌面與網頁 agent 餵入*扁平化、
已編號、依視口修剪*的文字區塊(「無障礙樹作為文字觀測」模式),再依索引操作(「click [12]」)。本功能建立該觀測
與其背後的索引,與 :doc:`v138_features_doc` 及 ``set_of_marks`` 搭配。

純標準函式庫,作用於純元素字典(``role`` / ``name`` / ``x`` / ``y`` / ``width`` / ``height``,可含巢狀
``children``),因此完全可單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (serialize_observation, observation_index,
                                 flatten_tree)

    text = serialize_observation(a11y_tree, viewport=(0, 0, 1920, 1080),
                                 max_elements=60)
    # [0] button "Save" @(30,20)
    # [1] textbox "Search" @(140,20)
    # ... 把 `text` 餵給模型;它回覆「click [1]」

    target = observation_index(a11y_tree)[1]      # [1] 背後的結構化元素
    click(*[target["x"] + target["width"] // 2, target["y"] + target["height"] // 2])

``flatten_tree`` 扁平化巢狀元素樹,預設只保留互動角色。``observation_index`` 裁切到 ``viewport``、由上到下 /
由左到右排序、上限 ``max_elements`` 並指派穩定 ``index``。``serialize_observation`` 將其渲染為
``[i] role "name" @(cx,cy)`` 行。

執行器命令
----------

``AC_serialize_observation``(``elements`` / ``viewport`` / ``max_elements`` → ``{observation, count}``)與
``AC_observation_index``(相同輸入 → ``{count, elements}``)。它們以 MCP 工具 ``ac_serialize_observation`` /
``ac_observation_index`` 以及 Script Builder 中 **Native UI** 分類下的命令提供。
