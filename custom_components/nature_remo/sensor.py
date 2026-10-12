"""Remo本体の温度・湿度センサー。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import NatureRemoConfigEntry, NatureRemoCoordinator
from .entity import remo_device_info
from .models import RemoDeviceStatus


@dataclass(frozen=True, kw_only=True)
class NatureRemoSensorEntityDescription(SensorEntityDescription):
    """センサーの定義。keyは既存連携のunique_idで使う `newest_events` のキー。"""

    name_suffix: str
    value_fn: Callable[[RemoDeviceStatus], float | None]


SENSORS: tuple[NatureRemoSensorEntityDescription, ...] = (
    NatureRemoSensorEntityDescription(
        key="te",
        name_suffix="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.temperature,
    ),
    NatureRemoSensorEntityDescription(
        key="hu",
        name_suffix="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.humidity,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NatureRemoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Remo本体が計測している値ごとにsensor entityを追加する。"""
    coordinator = entry.runtime_data
    async_add_entities(
        NatureRemoSensor(coordinator, status, description)
        for status in coordinator.data.devices.values()
        for description in SENSORS
        if description.value_fn(status) is not None
    )


class NatureRemoSensor(CoordinatorEntity[NatureRemoCoordinator], SensorEntity):
    """Remo本体のセンサー値。"""

    entity_description: NatureRemoSensorEntityDescription
    # 既存連携のentity名「Nature Remo {Remo本体名} Temperature」を変えないため
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: NatureRemoCoordinator,
        status: RemoDeviceStatus,
        description: NatureRemoSensorEntityDescription,
    ) -> None:
        """センサーのentityを作る。"""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = status.device.id
        self._attr_unique_id = (
            f"nature_remo_sensor_{status.device.id}_{description.key}"
        )
        self._attr_name = f"Nature Remo {status.device.name} {description.name_suffix}"
        self._attr_device_info = remo_device_info(status.device)

    @property
    @override
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data.devices

    @property
    @override
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(
            self.coordinator.data.devices[self._device_id]
        )
