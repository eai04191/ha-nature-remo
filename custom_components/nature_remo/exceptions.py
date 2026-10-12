"""Nature APIクライアントの例外。"""

from datetime import datetime


class NatureRemoError(Exception):
    """Nature APIの呼び出しに失敗したことを表す基底例外。"""


class NatureRemoConnectionError(NatureRemoError):
    """通信エラーまたはタイムアウト。"""


class NatureRemoAuthError(NatureRemoError):
    """アクセストークンが拒否された（HTTP 401）。"""


class NatureRemoRateLimitError(NatureRemoError):
    """レート制限に達した（HTTP 429）。"""

    def __init__(self, reset_at: datetime | None) -> None:
        """リセット時刻を保持する。ヘッダがなければNone。"""
        super().__init__(f"レート制限に達しました（リセット: {reset_at}）")
        self.reset_at = reset_at


class NatureRemoApiError(NatureRemoError):
    """401・429以外の成功でないHTTPステータス。"""

    def __init__(self, status: int, body: str) -> None:
        """ステータスと応答本文の先頭を保持する。"""
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status


class NatureRemoResponseError(NatureRemoError):
    """応答がJSONとして不正、または想定した形をしていない。"""
