"""Nature Remoの設定フロー。"""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import probatio

from .api import NatureRemoClient
from .const import DOMAIN
from .exceptions import NatureRemoAuthError, NatureRemoError

STEP_USER_SCHEMA = probatio.Schema({probatio.Required(CONF_API_KEY): str})


class NatureRemoConfigFlow(ConfigFlow, domain=DOMAIN):
    """アクセストークンを受け取り、Nature APIで検証してから登録する。

    既存連携（NaNaLinks/homeassistant_nature_remo）のconfig entryをそのまま読めるよう、
    version 1 / minor 1 と `data={"api_key": ...}` の形を変えない。
    """

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """アクセストークンの入力を受け付ける。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key: str = user_input[CONF_API_KEY]
            client = NatureRemoClient(async_get_clientsession(self.hass), api_key)
            try:
                user = await client.async_get_user()
            except NatureRemoAuthError:
                errors["base"] = "invalid_auth"
            except NatureRemoError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user.id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Nature Remo", data={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
