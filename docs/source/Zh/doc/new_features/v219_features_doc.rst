從像素形狀分類控制項
====================

Set-of-Marks 與元素提案器回傳*方框*,卻不告訴你*每個方框是什麼*。``form_fields.checkbox_state``
已能讀取一個已知是核取方塊的方框;缺少的是它之前的分類步驟——這個方框是核取方塊、單選鈕、按鈕、
文字欄位還是切換開關?``icon_classify`` 從低成本的幾何特徵(無需模型)回答此問題。

* :func:`box_features` ——擷取方框區域的 ``{aspect, fill, edge_density, circularity}``(客觀量測)。
* :func:`classify_widget` ——純函式:以記載的啟發式規則把特徵字典映射為控制項型別。
* :func:`classify_icon` ——組合兩者:把一個方框轉為 ``{type, features}``。

``classify_widget`` 為純函式且可完整測試;``box_features`` 延遲匯入 cv2 / numpy(模組無需它們即可匯入),
並重用 :func:`visual_match._to_gray`。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import classify_icon, classify_widget

    # 從截圖 + 方框:
    classify_icon("dialog.png", [120, 80, 16, 16])
    # {'type': 'checkbox', 'features': {'aspect': 1.0, 'fill': 0.12, ...}}

    # 從你已有的特徵:
    classify_widget({"aspect": 1.0, "circularity": 0.9, "fill": 0.4})  # 'radio'

啟發式規則:圓形方框(aspect ≈ 1、高 circularity)為 ``radio``;寬且圓潤為 ``toggle``;
近正方且稀疏為 ``checkbox``;寬且空心為 ``text_field``;寬且填滿為 ``button``;其餘為 ``icon``。
在預設誤判處,可讀取 ``features`` 套用你自己的規則微調——量測值才是耐用的部分。

執行器指令
----------

``AC_classify_widget``(``features`` JSON 物件 → ``{type}``,純函式)與
``AC_classify_icon``(``source`` 影像 + ``box`` ``[x, y, w, h]`` → ``{type, features}``)。
皆以對應的唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Image** 分類下)形式提供。
