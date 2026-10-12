"""Nature Remo連携。"""

from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NatureRemoClient
from .coordinator import NatureRemoConfigEntry, NatureRemoCoordinator

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: NatureRemoConfigEntry) -> bool:
    """設定エントリを読み込む。"""
    client = NatureRemoClient(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    coordinator = NatureRemoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NatureRemoConfigEntry) -> bool:
    """設定エントリを外す。"""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
