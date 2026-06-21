HTTP 錄製與重播卡帶
==================

HTTP 用戶端把 ``urllib`` 傳輸寫死,因此一個驅動真實 API 的流程,若沒有可連線的線上伺服器便無法在
CI 重跑。用戶端現在開放 ``build_call`` / ``urllib_transport`` 接縫,本層在其上加入 VCR 風格的
**卡帶**:重播會為相符的請求回傳已錄製的回應(純粹、不連網 —— 對 CI 最有價值的一半),而錄製則是
在實際傳輸之上的薄薄一層轉送。

純標準函式庫(``json``);不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import Cassette, CassetteMissError
    from je_auto_control.utils.http_client import build_call, urllib_transport

    # 對線上伺服器錄製一次,然後存檔:
    cassette = Cassette()
    transport = cassette.recording_transport(urllib_transport)
    transport(build_call("https://api.example.com/users/1", "GET"))
    cassette.save("users.cassette.json")

    # 之後永遠重播 —— 具決定性、離線:
    cassette = Cassette.load("users.cassette.json")
    response = cassette.replay(build_call("https://api.example.com/users/1", "GET"))
    assert response["status"] == 200

``build_call`` 把請求參數轉成純 dict(url、method、headers、body、timeout)而不碰網路;
``urllib_transport`` 負責實際發送。``Cassette.record`` 儲存一組請求/回應;``replay`` 為符合
``match_on``(預設 ``("method", "url")``,可加 ``"body"``)的請求回傳已錄製的回應,找不到時拋出
``CassetteMissError``。``replay_transport`` / ``recording_transport`` 回傳可直接替換的傳輸,讓既有
呼叫端在不變動下把實際流量換成卡帶。

執行器命令
----------

``AC_http_replay`` 接受 ``cassette``(interactions 清單或 ``{interactions}``,可為 JSON 字串)、
``url`` 與選用的 ``method``,在不連網的情況下回傳已錄製的 ``{response}``。它以 MCP 工具
``ac_http_replay`` 以及 Script Builder 中 **Data** 分類下的命令提供。
