"""config flowのテスト。"""

from http import HTTPStatus

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.nature_remo.const import DOMAIN

from .conftest import API, TOKEN, FakeNatureApi

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def test_create_entry(hass: HomeAssistant, fake_api: FakeNatureApi) -> None:
    """既存連携と同じ形（version 1.1、dataはapi_keyのみ）のentryを作る。"""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": TOKEN}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Nature Remo"
    assert result["data"] == {"api_key": TOKEN}
    entry = result["result"]
    assert (entry.version, entry.minor_version) == (1, 1)
    assert entry.unique_id == "user-1"
    assert entry.options == {}


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (HTTPStatus.UNAUTHORIZED, "invalid_auth"),
        (HTTPStatus.INTERNAL_SERVER_ERROR, "cannot_connect"),
        (HTTPStatus.TOO_MANY_REQUESTS, "cannot_connect"),
    ],
)
async def test_errors_then_recover(
    hass: HomeAssistant, fake_api: FakeNatureApi, status: HTTPStatus, error: str
) -> None:
    """検証に失敗したらフォームにエラーを出し、直れば登録できる。"""
    fake_api.fail(status)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    fake_api.failure = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """通信エラーはcannot_connectにする。"""
    aioclient_mock.get(f"{API}/1/users/me", exc=TimeoutError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": TOKEN}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_already_configured(hass: HomeAssistant, fake_api: FakeNatureApi) -> None:
    """同じNatureアカウントは二重登録しない。"""
    MockConfigEntry(
        domain=DOMAIN, unique_id="user-1", data={"api_key": TOKEN}
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
