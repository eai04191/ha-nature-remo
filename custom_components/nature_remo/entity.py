"""entityで共有する処理。"""

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER
from .models import RemoDevice


def remo_device_info(device: RemoDevice) -> DeviceInfo:
    """Remo本体のデバイス情報。climateとsensorは同じRemo本体のデバイスにぶら下げる。"""
    return DeviceInfo(
        identifiers={(DOMAIN, device.id)},
        name=device.name,
        manufacturer=MANUFACTURER,
        sw_version=device.firmware_version,
    )
