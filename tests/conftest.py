"""テスト共通のfixture。"""

from collections.abc import Generator
import copy
from http import HTTPStatus
import re
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.nature_remo.const import DOMAIN

from .fixtures import APPLIANCES, DEVICES, USER

API = "https://api.nature.global"
TOKEN = "test-token"
AIRCON_SETTINGS_URL = re.compile(
    rf"^{re.escape(API)}/1/appliances/([^/]+)/aircon_settings$"
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """custom_componentsを読み込めるようにする。"""


class FakeNatureApi:
    """状態を持ち、Nature APIのように応答するfake。

    操作APIは受け取ったフォームを設定に反映して返し、以後の一覧取得にも反映する。
    運転モードだけを変えたときは、モードごとに記憶された温度（除湿・送風は空文字）を返す。
    """

    def __init__(self) -> None:
        """fixtureの複製から状態を作る。"""
        self.user: dict[str, Any] = copy.deepcopy(USER)
        self.devices: list[dict[str, Any]] = copy.deepcopy(DEVICES)
        self.appliances: list[dict[str, Any]] = copy.deepcopy(APPLIANCES)
        self.mode_temps: dict[str, str] = {
            "cool": "26",
            "warm": "22",
            "dry": "",
            "blow": "",
            "auto": "0",
        }
        self.posts: list[tuple[str, dict[str, str]]] = []
        self.get_count = 0
        # 設定すると全エンドポイントがこの応答を返す
        self.failure: AiohttpClientMockResponse | None = None

    def register(self, aioclient_mock: AiohttpClientMocker) -> None:
        """aioclient_mockにエンドポイントを登録する。"""
        aioclient_mock.get(f"{API}/1/users/me", side_effect=self._get)
        aioclient_mock.get(f"{API}/1/devices", side_effect=self._get)
        aioclient_mock.get(f"{API}/1/appliances", side_effect=self._get)
        aioclient_mock.post(AIRCON_SETTINGS_URL, side_effect=self._post)

    def fail(
        self,
        status: HTTPStatus,
        *,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        """以後の全リクエストを失敗させる。"""
        self.failure = AiohttpClientMockResponse(
            "any", URL(API), status=status, text=text, headers=headers
        )

    def aircon(self, appliance_id: str) -> dict[str, Any]:
        """家電IDでエアコンの生データを返す。"""
        return next(a for a in self.appliances if a["id"] == appliance_id)

    async def _get(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        if self.failure is not None:
            return self.failure
        self.get_count += 1
        bodies: dict[str, object] = {
            "/1/users/me": self.user,
            "/1/devices": self.devices,
            "/1/appliances": self.appliances,
        }
        return AiohttpClientMockResponse(method, url, json=bodies[url.path])

    async def _post(
        self, method: str, url: URL, data: dict[str, str]
    ) -> AiohttpClientMockResponse:
        if self.failure is not None:
            return self.failure
        match = AIRCON_SETTINGS_URL.match(str(url))
        assert match is not None
        appliance_id = match.group(1)
        self.posts.append((appliance_id, dict(data)))
        settings = self.aircon(appliance_id)["settings"]
        self._apply(settings, data)
        return AiohttpClientMockResponse(method, url, json=settings)

    def _apply(self, settings: dict[str, str], form: dict[str, str]) -> None:
        if "operation_mode" in form:
            if form["operation_mode"] != settings["mode"]:
                settings["temp"] = self.mode_temps[form["operation_mode"]]
            settings["mode"] = form["operation_mode"]
            settings["button"] = ""
        fields = {
            "temperature": "temp",
            "air_volume": "vol",
            "air_direction": "dir",
            "button": "button",
        }
        for form_key, settings_key in fields.items():
            if form_key in form:
                settings[settings_key] = form[form_key]


@pytest.fixture
def fake_api(aioclient_mock: AiohttpClientMocker) -> FakeNatureApi:
    """登録済みのfake APIを返す。"""
    api = FakeNatureApi()
    api.register(aioclient_mock)
    return api


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """既存連携が作ったものと同じ形のconfig entry（unique_idなし、optionsは空）。"""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Nature Remo",
        version=1,
        minor_version=1,
        data={"api_key": TOKEN},
        options={},
        unique_id=None,
    )


@pytest.fixture
def mock_setup_entry() -> Generator[None]:
    """Config flowのテストで実際のセットアップを走らせない。"""
    with patch("custom_components.nature_remo.async_setup_entry", return_value=True):
        yield


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Config entryを登録して読み込む。"""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, fake_api: FakeNatureApi, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """読み込み済みのconfig entry。"""
    await setup_integration(hass, config_entry)
    return config_entry
