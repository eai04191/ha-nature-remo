"""APIクライアントと応答の検証のテスト。"""

from datetime import UTC, datetime
from http import HTTPStatus

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.nature_remo.api import AirconSettingsRequest, NatureRemoClient
from custom_components.nature_remo.exceptions import (
    NatureRemoApiError,
    NatureRemoAuthError,
    NatureRemoConnectionError,
    NatureRemoRateLimitError,
    NatureRemoResponseError,
)
from custom_components.nature_remo.models import TemperatureOption

from .conftest import API, TOKEN, FakeNatureApi


@pytest.fixture
async def client(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> NatureRemoClient:
    """HAの共有セッション（aioclient_mockで差し替え済み）を使うクライアント。"""
    return NatureRemoClient(async_get_clientsession(hass), TOKEN)


async def test_get_devices(client: NatureRemoClient, fake_api: FakeNatureApi) -> None:
    """Remo本体ごとに温度・湿度を読み、未計測ならNoneにする。"""
    devices = await client.async_get_devices()

    assert [(d.device.id, d.temperature, d.humidity) for d in devices] == [
        ("dev-living", 25.4, 48),
        ("dev-study", 22.1, 55),
        ("dev-nano", None, None),
    ]
    assert devices[0].device.name == "Living Remo"


async def test_get_devices_null_newest_events(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """newest_eventsはnullableなので、nullならセンサー値なしとして扱う。"""
    fake_api.devices[0]["newest_events"] = None

    devices = await client.async_get_devices()

    assert devices[0].temperature is None


async def test_get_aircons(client: NatureRemoClient, fake_api: FakeNatureApi) -> None:
    """エアコン以外を除き、範囲の空文字を取り除き、空文字の設定温度をNoneにする。"""
    aircons = await client.async_get_aircons()

    assert [a.id for a in aircons] == ["ac-living", "ac-study", "ac-bedroom"]
    living, study, bedroom = aircons
    assert living.device.id == "dev-living"
    assert living.settings.temperature == 26
    assert living.modes["cool"].air_directions == ()
    assert living.modes["blow"].temperatures == ()
    assert (
        TemperatureOption(value=26.5, raw="26.5") in living.modes["cool"].temperatures
    )
    assert living.modes["dry"].temperatures[0] == TemperatureOption(value=-2, raw="-2")
    assert study.settings.mode == "dry"
    assert study.settings.temperature is None
    assert bedroom.settings.is_power_off


async def test_update_aircon_settings(
    client: NatureRemoClient,
    fake_api: FakeNatureApi,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """フォームにはNoneでない項目だけを入れ、認証ヘッダを付ける。"""
    settings = await client.async_update_aircon_settings(
        "ac-living", AirconSettingsRequest(operation_mode="dry")
    )

    assert fake_api.posts == [("ac-living", {"operation_mode": "dry"})]
    assert settings.mode == "dry"
    assert settings.temperature is None
    _, _, _, headers = aioclient_mock.mock_calls[-1]
    assert headers == {"Authorization": f"Bearer {TOKEN}"}


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (HTTPStatus.UNAUTHORIZED, NatureRemoAuthError),
        (HTTPStatus.INTERNAL_SERVER_ERROR, NatureRemoApiError),
        (HTTPStatus.BAD_REQUEST, NatureRemoApiError),
    ],
)
async def test_http_errors(
    client: NatureRemoClient,
    fake_api: FakeNatureApi,
    status: HTTPStatus,
    error: type[Exception],
) -> None:
    """成功でないステータスは例外にする。"""
    fake_api.fail(status, text='{"code":0,"message":"error"}')

    with pytest.raises(error):
        await client.async_get_devices()


async def test_rate_limit_with_reset(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """429はリセット時刻つきの例外にする。"""
    fake_api.fail(
        HTTPStatus.TOO_MANY_REQUESTS, headers={"X-Rate-Limit-Reset": "1791763200"}
    )

    with pytest.raises(NatureRemoRateLimitError) as exc_info:
        await client.async_get_devices()

    assert exc_info.value.reset_at == datetime(2026, 10, 12, tzinfo=UTC)


async def test_rate_limit_without_reset(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """X-Rate-Limit-Resetがなくても落ちずに429として扱う。"""
    fake_api.fail(HTTPStatus.TOO_MANY_REQUESTS)

    with pytest.raises(NatureRemoRateLimitError) as exc_info:
        await client.async_get_devices()

    assert exc_info.value.reset_at is None


async def test_success_without_rate_limit_headers(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """レート制限ヘッダのない成功応答も扱える。"""
    assert len(await client.async_get_devices()) == 3


async def test_invalid_json(
    client: NatureRemoClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """JSONでない応答は例外にする。"""
    aioclient_mock.get(f"{API}/1/devices", text="<html>maintenance</html>")

    with pytest.raises(NatureRemoResponseError):
        await client.async_get_devices()


@pytest.mark.parametrize(
    "body",
    [
        {"devices": []},
        [{"id": "dev-1"}],
        [{"id": "dev-1", "name": "Remo", "firmware_version": "1", "newest_events": 1}],
        [
            {
                "id": "dev-1",
                "name": "Remo",
                "firmware_version": "1",
                "newest_events": {"te": {"val": "25"}},
            }
        ],
        None,
    ],
)
async def test_unexpected_device_shape(
    client: NatureRemoClient, aioclient_mock: AiohttpClientMocker, body: object
) -> None:
    """想定外の形は黙って既定値にせず例外にする。"""
    aioclient_mock.get(f"{API}/1/devices", json=body)

    with pytest.raises(NatureRemoResponseError):
        await client.async_get_devices()


async def test_aircon_without_settings(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """エアコンにsettingsがなければ例外にする。"""
    fake_api.appliances[0]["settings"] = None

    with pytest.raises(NatureRemoResponseError):
        await client.async_get_aircons()


async def test_non_numeric_range_temperature(
    client: NatureRemoClient, fake_api: FakeNatureApi
) -> None:
    """範囲の温度は空文字以外が数値でなければ例外にする。"""
    fake_api.appliances[0]["aircon"]["range"]["modes"]["cool"]["temp"] = ["hot"]

    with pytest.raises(NatureRemoResponseError):
        await client.async_get_aircons()


@pytest.mark.parametrize("exc", [ClientError("boom"), TimeoutError()])
async def test_connection_errors(
    client: NatureRemoClient, aioclient_mock: AiohttpClientMocker, exc: Exception
) -> None:
    """通信エラーとタイムアウトは接続エラーにする。"""
    aioclient_mock.get(f"{API}/1/devices", exc=exc)

    with pytest.raises(NatureRemoConnectionError):
        await client.async_get_devices()
