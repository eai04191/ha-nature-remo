"""セットアップと定期更新のテスト。"""

from http import HTTPStatus

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .conftest import FakeNatureApi


async def test_setup_and_unload(
    hass: HomeAssistant,
    fake_api: FakeNatureApi,
    loaded_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """既存連携が作ったentryをそのまま読み込み、外せる。"""
    assert loaded_entry.state is ConfigEntryState.LOADED
    # 1回の更新で /1/devices と /1/appliances を1回ずつ取得する
    assert [str(url) for _, url, _, _ in aioclient_mock.mock_calls] == [
        "https://api.nature.global/1/devices",
        "https://api.nature.global/1/appliances",
    ]

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    # 直前のassertでmypyが状態をLOADEDに絞り込むため、型を広げて読み直す
    state: ConfigEntryState = loaded_entry.state
    assert state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_on_api_error(
    hass: HomeAssistant, fake_api: FakeNatureApi, config_entry: MockConfigEntry
) -> None:
    """初回取得に失敗したら再試行待ちにする。"""
    fake_api.fail(HTTPStatus.INTERNAL_SERVER_ERROR)
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
