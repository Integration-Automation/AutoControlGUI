用戶端速率限制
=============

框架過去有 ``RetryPolicy`` / ``CircuitBreaker``(用於從失敗中*復原*)以及 FIFO 的
``work_queue``,卻沒有任何東西能塑形呼叫的*速率* —— 因此猛打外部 API 的流程沒有辦法守在配額
之內。本功能補上兩個標準限制器,外加一個前緣觸發的 throttle,全都以可注入的時鐘實作,因此在測試
中具決定性(不需真的睡眠)。

* :class:`TokenBucket` —— 平滑速率搭配突發容量(惰性回填)。
* :class:`SlidingWindowLimiter` —— 每個滾動視窗固定的呼叫額度(Cloudflare 的 O(1) 加權計數
  近似)。
* :func:`throttle` —— 一個讓函式在每個間隔內最多觸發一次的裝飾器。

純標準函式庫(``threading`` 用於鎖,``time`` 僅作為預設時鐘);不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import TokenBucket, SlidingWindowLimiter, throttle

    # 每秒 5 個請求,可突發到 10
    bucket = TokenBucket(rate=5, capacity=10)
    if bucket.try_acquire():
        call_api()                      # 非阻塞:False 時略過 / 排入佇列
    bucket.acquire()                    # 或阻塞直到有 token 釋出

    # 每 60 秒滾動視窗最多 100 次呼叫
    window = SlidingWindowLimiter(limit=100, window_s=60)
    if window.try_acquire():
        call_api()

    @throttle(2.0)                      # 每 2 秒最多觸發一次
    def on_event(payload):
        ...

``TokenBucket.try_acquire`` 在有 token 時取用;``acquire`` 會阻塞(可選 ``timeout``);
``time_until_available`` 回報等待時間,讓排程器自行調速。每個限制器都接受 ``clock=``(``acquire``
另接受 ``sleep=``),因此整體可在 CI 以假時鐘演練 —— 沒有真正的延遲。

執行器命令
----------

``AC_rate_limit`` 接受限制器 ``name`` 以及 ``rate`` / ``capacity`` / ``n``,嘗試從該具名 token
bucket(首次使用時建立)取用 ``n`` 個 token,回傳 ``{acquired, tokens, wait}``,讓流程可閘控或
延後某個動作。同一操作亦以 MCP 工具 ``ac_rate_limit`` 以及 Script Builder 中 **Flow** 分類下的
命令提供。
