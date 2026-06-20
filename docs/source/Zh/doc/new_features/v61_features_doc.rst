JSON Web Token(JWT)
===================

RPA 流程經常需要為其驅動的 API 簽發或驗證 bearer token,但框架過去只有 HMAC *檔案*簽章
(``action_signing``)以及綁定 ACME 的 RS256 JWS(``acme_v2``)—— 兩者都不會產生或驗證精簡的
bearer JWT。本功能補上一個聚焦、純標準函式庫的 JWT 編解碼器(HMAC 家族)並含完整的宣告驗證,
設計上可直接餵入 ``http_request`` 的 bearer 驗證。

純標準函式庫(``hmac`` + ``hashlib`` + ``base64`` + ``json``);時鐘可注入,因此 ``exp`` /
``nbf`` 檢查具決定性。不匯入 ``PySide6``。

安全性
------

解碼器預設即安全:

* **拒絕 ``alg: "none"``** 以及任何呼叫端未明確列入允許清單的演算法,藉此擊敗經典的演算法
  混淆 / 降級攻擊;
* 以 ``hmac.compare_digest``(常數時間)比較簽章;
* RSA/EC 演算法(RS256/ES256)刻意**不在範圍內** —— 它們需要第三方加密函式庫。

無頭 API
--------

.. code-block:: python

    from je_auto_control import encode_jwt, decode_jwt, ClaimsPolicy

    token = encode_jwt({"sub": "user1", "aud": "api", "exp": 1893456000}, secret)
    # -> "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...."

    # 預設政策:僅 HS256、驗證 exp/nbf、不檢查 audience/issuer
    claims = decode_jwt(token, secret)

    # 以 ClaimsPolicy 收緊 audience / issuer / leeway / algorithms
    policy = ClaimsPolicy(algorithms=("HS256",), audience="api",
                          issuer="my-service", leeway=30)
    claims = decode_jwt(token, secret, policy)

``encode_jwt`` 以 ``HS256`` / ``HS384`` / ``HS512`` 簽出精簡的
``header.payload.signature`` token。``decode_jwt`` 先驗證簽章,再以一份 :class:`ClaimsPolicy`
(含 ``leeway`` 的 ``exp`` / ``nbf``、``aud`` 成員資格、``iss`` 比對)使用可注入的 ``now`` 驗證
標準宣告;失敗時拋出 ``ExpiredTokenError`` / ``InvalidSignatureError`` / ``JwtError``。簽出的
token 可直接接上 HTTP 用戶端:

.. code-block:: python

    from je_auto_control import http_request
    http_request("https://api.example.com/me",
                 auth={"type": "bearer", "token": token})

執行器命令
----------

``AC_jwt_encode`` 接受 ``claims``(dict 或 JSON 字串)、``key`` 與選用的 ``alg``,回傳
``{token}``。``AC_jwt_decode`` 接受 ``token``、``key`` 與選用的 ``algorithms`` /
``audience`` / ``leeway``,回傳 ``{ok, claims}``(或 ``{ok: false, error}``,讓流程可在不拋出
例外的情況下分支)。兩者皆以 MCP 工具 ``ac_jwt_encode`` / ``ac_jwt_decode`` 以及 Script Builder
中 **Security** 分類下的命令提供。
