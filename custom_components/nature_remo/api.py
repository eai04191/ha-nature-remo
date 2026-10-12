"""Nature Remo Cloud APIのクライアント。"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http import HTTPStatus
import json
import logging

from aiohttp import ClientError, ClientSession, ClientTimeout
from multidict import CIMultiDictProxy

from .exceptions import (
    NatureRemoApiError,
    NatureRemoAuthError,
    NatureRemoConnectionError,
    NatureRemoRateLimitError,
    NatureRemoResponseError,
)
from .models import (
    Aircon,
    AirconSettings,
    RemoDeviceStatus,
    User,
    parse_aircon_settings,
    parse_aircons,
    parse_devices,
    parse_user,
)

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://api.nature.global"
REQUEST_TIMEOUT = ClientTimeout(total=30)


@dataclass(frozen=True, slots=True, kw_only=True)
class AirconSettingsRequest:
    """`POST /1/appliances/{id}/aircon_settings` のフォーム。Noneの項目は送らない。"""

    operation_mode: str | None = None
    temperature: str | None = None
    air_volume: str | None = None
    air_direction: str | None = None
    button: str | None = None

    def to_form(self) -> dict[str, str]:
        """送信するフォームを返す。"""
        return {key: value for key, value in asdict(self).items() if value is not None}


class NatureRemoClient:
    """Nature APIを呼び、応答を型付きデータで返す。失敗は例外で表す。"""

    def __init__(self, session: ClientSession, access_token: str) -> None:
        """HAの共有セッションとアクセストークンで初期化する。"""
        self._session = session
        self._access_token = access_token

    async def async_get_user(self) -> User:
        """トークンの持ち主を取得する。"""
        return parse_user(await self._request("GET", "/1/users/me"))

    async def async_get_devices(self) -> tuple[RemoDeviceStatus, ...]:
        """Remo本体の一覧とセンサー値を取得する。"""
        return parse_devices(await self._request("GET", "/1/devices"))

    async def async_get_aircons(self) -> tuple[Aircon, ...]:
        """家電一覧のうちエアコンを取得する。"""
        return parse_aircons(await self._request("GET", "/1/appliances"))

    async def async_update_aircon_settings(
        self, appliance_id: str, request: AirconSettingsRequest
    ) -> AirconSettings:
        """エアコンの設定を変更し、変更後の設定を返す。"""
        path = f"/1/appliances/{appliance_id}/aircon_settings"
        return parse_aircon_settings(
            await self._request("POST", path, request.to_form())
        )

    async def _request(
        self, method: str, path: str, form: Mapping[str, str] | None = None
    ) -> object:
        try:
            async with self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                data=form,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                body = await response.text()
                status = response.status
                headers = response.headers
        except TimeoutError as err:
            raise NatureRemoConnectionError(f"{method} {path}: タイムアウト") from err
        except ClientError as err:
            raise NatureRemoConnectionError(f"{method} {path}: {err}") from err

        _LOGGER.debug(
            "%s %s -> %s（残りリクエスト数: %s）",
            method,
            path,
            status,
            headers.get("X-Rate-Limit-Remaining"),
        )
        _raise_for_status(status, headers, body)
        try:
            data: object = json.loads(body)
        except json.JSONDecodeError as err:
            raise NatureRemoResponseError(f"{method} {path}: JSONではない応答") from err
        return data


def _raise_for_status(status: int, headers: CIMultiDictProxy[str], body: str) -> None:
    if status == HTTPStatus.UNAUTHORIZED:
        raise NatureRemoAuthError("アクセストークンが拒否されました")
    if status == HTTPStatus.TOO_MANY_REQUESTS:
        raise NatureRemoRateLimitError(_rate_limit_reset(headers))
    if not HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
        raise NatureRemoApiError(status, body)


def _rate_limit_reset(headers: CIMultiDictProxy[str]) -> datetime | None:
    """X-Rate-Limit-Reset（epoch秒）を読む。ヘッダがない・数値でない場合はNone。"""
    raw = headers.get("X-Rate-Limit-Reset")
    if raw is None or not raw.isdigit():
        return None
    return datetime.fromtimestamp(int(raw), tz=UTC)
