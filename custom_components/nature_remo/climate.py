"""Nature Remoで操作するエアコン。"""

from itertools import pairwise
import math
from typing import Any, Final, override

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AirconSettingsRequest
from .coordinator import NatureRemoConfigEntry, NatureRemoCoordinator
from .entity import remo_device_info
from .exceptions import NatureRemoError
from .models import BUTTON_POWER_OFF, Aircon, ModeRange, TemperatureOption

# HAのモードとNature APIの運転モード。並び順はhvac_modesの表示順（既存連携と同じ）
MODE_MAP: Final[dict[HVACMode, str]] = {
    HVACMode.COOL: "cool",
    HVACMode.DRY: "dry",
    HVACMode.HEAT: "warm",
    HVACMode.FAN_ONLY: "blow",
    HVACMode.AUTO: "auto",
}
TEMPERATURE_TOLERANCE: Final = 1e-6
REMO_MODE_TO_HVAC: Final[dict[str, HVACMode]] = {v: k for k, v in MODE_MAP.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NatureRemoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """エアコンごとにclimate entityを追加する。"""
    coordinator = entry.runtime_data
    async_add_entities(
        NatureRemoClimate(coordinator, aircon)
        for aircon in coordinator.data.aircons.values()
    )


class NatureRemoClimate(CoordinatorEntity[NatureRemoCoordinator], ClimateEntity):
    """Nature Remoに登録したエアコン。

    対応モード・温度・風量・風向は `aircon.range.modes` から、現在の設定は
    `settings` から、室温・湿度は同じRemo本体のセンサー値から決める。
    """

    # 既存連携のentity名「Nature Remo {nickname}」とentity_idを変えないため
    _attr_has_entity_name = False
    # 既存連携と同じく摂氏固定。aircon.tempUnitは参照しない
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: NatureRemoCoordinator, aircon: Aircon) -> None:
        """エアコンのentityを作る。"""
        super().__init__(coordinator)
        self._appliance_id = aircon.id
        self._attr_unique_id = f"nature_remo_climate_{aircon.id}"
        self._attr_name = f"Nature Remo {aircon.nickname}"
        self._attr_device_info = remo_device_info(aircon.device)
        # 一覧から消えて利用不可の間もHAはhvac_modes等の属性を読むため、最後の値を持つ
        self._aircon = aircon

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        aircon = self.coordinator.data.aircons.get(self._appliance_id)
        if aircon is not None:
            self._aircon = aircon
        super()._handle_coordinator_update()

    @property
    def _mode_range(self) -> ModeRange | None:
        """現在（電源OFF中は最後）の運転モードの設定可能範囲。"""
        return self._aircon.modes.get(self._aircon.settings.mode)

    @property
    @override
    def available(self) -> bool:
        return super().available and self._appliance_id in self.coordinator.data.aircons

    @property
    @override
    def supported_features(self) -> ClimateEntityFeature:
        features = ClimateEntityFeature(0)
        mode_range = self._mode_range
        if mode_range is None:
            return features
        if mode_range.temperatures:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if mode_range.air_volumes:
            features |= ClimateEntityFeature.FAN_MODE
        if mode_range.air_directions:
            features |= ClimateEntityFeature.SWING_MODE
        return features

    @property
    @override
    def hvac_modes(self) -> list[HVACMode]:
        modes = self._aircon.modes
        return [HVACMode.OFF] + [
            hvac for hvac, remo in MODE_MAP.items() if remo in modes
        ]

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        settings = self._aircon.settings
        if settings.is_power_off:
            return HVACMode.OFF
        return REMO_MODE_TO_HVAC.get(settings.mode)

    @property
    @override
    def current_temperature(self) -> float | None:
        status = self.coordinator.data.devices.get(self._aircon.device.id)
        return None if status is None else status.temperature

    @property
    @override
    def current_humidity(self) -> float | None:
        status = self.coordinator.data.devices.get(self._aircon.device.id)
        return None if status is None else status.humidity

    @property
    @override
    def target_temperature(self) -> float | None:
        if not self._temperature_values:
            return None
        return self._aircon.settings.temperature

    @property
    @override
    def min_temp(self) -> float:
        values = self._temperature_values
        return min(values) if values else super().min_temp

    @property
    @override
    def max_temp(self) -> float:
        values = self._temperature_values
        return max(values) if values else super().max_temp

    @property
    @override
    def target_temperature_step(self) -> float | None:
        """設定可能な温度の最小の刻み。候補が1つ以下ならHAの既定に任せる。"""
        values = sorted(set(self._temperature_values))
        steps = [b - a for a, b in pairwise(values)]
        return min(steps) if steps else None

    @property
    @override
    def fan_modes(self) -> list[str] | None:
        mode_range = self._mode_range
        return list(mode_range.air_volumes) if mode_range else None

    @property
    @override
    def fan_mode(self) -> str | None:
        return _selected(self._aircon.settings.air_volume, self.fan_modes)

    @property
    @override
    def swing_modes(self) -> list[str] | None:
        mode_range = self._mode_range
        return list(mode_range.air_directions) if mode_range else None

    @property
    @override
    def swing_mode(self) -> str | None:
        return _selected(self._aircon.settings.air_direction, self.swing_modes)

    @property
    def _temperature_values(self) -> list[float]:
        mode_range = self._mode_range
        if mode_range is None:
            return []
        return [option.value for option in mode_range.temperatures]

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._async_send(AirconSettingsRequest(button=BUTTON_POWER_OFF))
            return
        await self._async_send(
            AirconSettingsRequest(operation_mode=self._remo_mode_for(hvac_mode))
        )

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        hvac_mode: HVACMode | None = kwargs.get(ATTR_HVAC_MODE)
        temperature: float = kwargs[ATTR_TEMPERATURE]
        remo_mode = (
            self._aircon.settings.mode
            if hvac_mode is None
            else self._remo_mode_for(hvac_mode)
        )
        option = self._temperature_option(remo_mode, temperature)
        await self._async_send(
            AirconSettingsRequest(operation_mode=remo_mode, temperature=option.raw)
        )

    @override
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._async_send(
            AirconSettingsRequest(
                operation_mode=self._aircon.settings.mode, air_volume=fan_mode
            )
        )

    @override
    async def async_set_swing_mode(self, swing_mode: str) -> None:
        await self._async_send(
            AirconSettingsRequest(
                operation_mode=self._aircon.settings.mode, air_direction=swing_mode
            )
        )

    def _remo_mode_for(self, hvac_mode: HVACMode) -> str:
        remo_mode = MODE_MAP.get(hvac_mode)
        if remo_mode is None or remo_mode not in self._aircon.modes:
            raise ServiceValidationError(
                f"{self.name}は運転モード{hvac_mode}に対応していません"
            )
        return remo_mode

    def _temperature_option(
        self, remo_mode: str, temperature: float
    ) -> TemperatureOption:
        mode_range = self._aircon.modes[remo_mode]
        for option in mode_range.temperatures:
            # HAの表示単位が華氏だと摂氏への変換で微小な誤差が出るため許容する
            if math.isclose(option.value, temperature, abs_tol=TEMPERATURE_TOLERANCE):
                return option
        allowed = ", ".join(option.raw for option in mode_range.temperatures)
        raise ServiceValidationError(
            f"{self.name}の運転モード{remo_mode}では{temperature}℃を設定できません"
            f"（設定可能: {allowed or 'なし'}）"
        )

    async def _async_send(self, request: AirconSettingsRequest) -> None:
        """設定を送り、応答の設定を即時反映してからcoordinatorを更新する。"""
        try:
            settings = await self.coordinator.client.async_update_aircon_settings(
                self._appliance_id, request
            )
        except NatureRemoError as err:
            raise HomeAssistantError(f"{self.name}の操作に失敗しました: {err}") from err
        self.coordinator.async_apply_aircon_settings(self._appliance_id, settings)
        await self.coordinator.async_request_refresh()


def _selected(value: str, options: list[str] | None) -> str | None:
    """選択肢にある値だけを現在値として返す。空文字（自動）などはNone。"""
    if options and value in options:
        return value
    return None
