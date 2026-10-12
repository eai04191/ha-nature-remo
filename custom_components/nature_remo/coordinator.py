"""Nature APIを定期取得するcoordinator。"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NatureRemoClient
from .const import DOMAIN, UPDATE_INTERVAL
from .exceptions import NatureRemoError, NatureRemoRateLimitError
from .models import Aircon, AirconSettings, RemoDeviceStatus

_LOGGER = logging.getLogger(__name__)

type NatureRemoConfigEntry = ConfigEntry[NatureRemoCoordinator]


@dataclass(frozen=True, slots=True)
class NatureRemoData:
    """1回の更新で得たRemo本体とエアコンの状態。キーはそれぞれのID。"""

    devices: Mapping[str, RemoDeviceStatus]
    aircons: Mapping[str, Aircon]

    def with_aircon_settings(
        self, appliance_id: str, settings: AirconSettings
    ) -> NatureRemoData:
        """指定したエアコンの設定だけを差し替えた複製を返す。"""
        aircons = dict(self.aircons)
        aircons[appliance_id] = aircons[appliance_id].with_settings(settings)
        return replace(self, aircons=aircons)


class NatureRemoCoordinator(DataUpdateCoordinator[NatureRemoData]):
    """`/1/devices` と `/1/appliances` をまとめて取得する。"""

    config_entry: NatureRemoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: NatureRemoConfigEntry,
        client: NatureRemoClient,
    ) -> None:
        """coordinatorを初期化する。"""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> NatureRemoData:
        try:
            devices = await self.client.async_get_devices()
            aircons = await self.client.async_get_aircons()
        except NatureRemoRateLimitError as err:
            raise UpdateFailed(
                f"Nature APIのレート制限に達しました: {err}",
                retry_after=_seconds_until(err.reset_at),
            ) from err
        except NatureRemoError as err:
            raise UpdateFailed(f"Nature APIからの取得に失敗しました: {err}") from err
        return NatureRemoData(
            devices={status.device.id: status for status in devices},
            aircons={aircon.id: aircon for aircon in aircons},
        )

    @callback
    def async_apply_aircon_settings(
        self, appliance_id: str, settings: AirconSettings
    ) -> None:
        """操作APIの応答で得た設定を即時反映する。"""
        self.async_set_updated_data(
            self.data.with_aircon_settings(appliance_id, settings)
        )


def _seconds_until(reset_at: datetime | None) -> float | None:
    if reset_at is None:
        return None
    return max((reset_at - datetime.now(UTC)).total_seconds(), 0.0)
