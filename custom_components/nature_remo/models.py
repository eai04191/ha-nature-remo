"""Nature APIの応答を検証して型付きデータに変換する。

フィールド名と型はNature APIのOpenAPI定義（2.0.0）に従う。
https://swagger.nature.global/swagger.json
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
from typing import cast

from .exceptions import NatureRemoResponseError

type JSONObject = Mapping[str, object]

APPLIANCE_TYPE_AIRCON = "AC"
BUTTON_POWER_OFF = "power-off"


@dataclass(frozen=True, slots=True)
class User:
    """`GET /1/users/me` の応答。"""

    id: str
    nickname: str


@dataclass(frozen=True, slots=True)
class RemoDevice:
    """Remo本体の識別情報。"""

    id: str
    name: str
    firmware_version: str


@dataclass(frozen=True, slots=True)
class RemoDeviceStatus:
    """`GET /1/devices` の1要素。センサー値は未搭載・未計測ならNone。"""

    device: RemoDevice
    temperature: float | None
    humidity: float | None


@dataclass(frozen=True, slots=True)
class TemperatureOption:
    """設定可能な温度。APIへはAPIが返した文字列をそのまま送る。"""

    value: float
    raw: str


@dataclass(frozen=True, slots=True)
class ModeRange:
    """`aircon.range.modes.<mode>` の設定可能範囲。

    空文字の要素は取り除く。APIの仕様では風量・風向の空文字は「自動」を意味するが、
    HAのfan_mode/swing_modeとして選べる値にはできないため、選択肢から外している。
    """

    temperatures: tuple[TemperatureOption, ...]
    air_volumes: tuple[str, ...]
    air_directions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AirconSettings:
    """エアコンの現在の設定（`AirconSettingsResponse`）。"""

    mode: str
    # 除湿・送風などでは空文字が返るため、数値でなければNoneにする
    temperature: float | None
    air_volume: str
    air_direction: str
    button: str

    @property
    def is_power_off(self) -> bool:
        """電源が切れているか。"""
        return self.button == BUTTON_POWER_OFF


@dataclass(frozen=True, slots=True)
class Aircon:
    """`GET /1/appliances` のうち種類がエアコンの要素。"""

    id: str
    nickname: str
    device: RemoDevice
    modes: Mapping[str, ModeRange]
    settings: AirconSettings

    def with_settings(self, settings: AirconSettings) -> Aircon:
        """設定だけを差し替えた複製を返す。"""
        return replace(self, settings=settings)


def parse_user(data: object) -> User:
    """`GET /1/users/me` の応答を変換する。"""
    obj = _as_object(data, "user")
    return User(id=_str(obj, "id", "user"), nickname=_str(obj, "nickname", "user"))


def parse_devices(data: object) -> tuple[RemoDeviceStatus, ...]:
    """`GET /1/devices` の応答を変換する。"""
    return tuple(
        _parse_device_status(item, f"devices[{index}]")
        for index, item in enumerate(_as_list(data, "devices"))
    )


def parse_aircons(data: object) -> tuple[Aircon, ...]:
    """`GET /1/appliances` の応答からエアコンだけを取り出して変換する。"""
    aircons: list[Aircon] = []
    for index, item in enumerate(_as_list(data, "appliances")):
        path = f"appliances[{index}]"
        obj = _as_object(item, path)
        if _str(obj, "type", path) == APPLIANCE_TYPE_AIRCON:
            aircons.append(_parse_aircon(obj, path))
    return tuple(aircons)


def parse_aircon_settings(data: object) -> AirconSettings:
    """`POST /1/appliances/{id}/aircon_settings` の応答を変換する。"""
    return _parse_settings(_as_object(data, "settings"), "settings")


def _parse_device(obj: JSONObject, path: str) -> RemoDevice:
    return RemoDevice(
        id=_str(obj, "id", path),
        name=_str(obj, "name", path),
        firmware_version=_str(obj, "firmware_version", path),
    )


def _parse_device_status(data: object, path: str) -> RemoDeviceStatus:
    obj = _as_object(data, path)
    events_path = f"{path}.newest_events"
    raw_events = obj.get("newest_events")
    events = {} if raw_events is None else _as_object(raw_events, events_path)
    return RemoDeviceStatus(
        device=_parse_device(obj, path),
        temperature=_sensor_value(events, "te", events_path),
        humidity=_sensor_value(events, "hu", events_path),
    )


def _sensor_value(events: JSONObject, key: str, path: str) -> float | None:
    event = events.get(key)
    if event is None:
        return None
    event_path = f"{path}.{key}"
    return _number(_as_object(event, event_path).get("val"), f"{event_path}.val")


def _parse_aircon(obj: JSONObject, path: str) -> Aircon:
    aircon_path = f"{path}.aircon"
    range_path = f"{aircon_path}.range"
    range_obj = _as_object(
        _as_object(obj.get("aircon"), aircon_path).get("range"), range_path
    )
    modes_path = f"{range_path}.modes"
    raw_modes = range_obj.get("modes")
    modes_obj = {} if raw_modes is None else _as_object(raw_modes, modes_path)
    return Aircon(
        id=_str(obj, "id", path),
        nickname=_str(obj, "nickname", path),
        device=_parse_device(
            _as_object(obj.get("device"), f"{path}.device"), f"{path}.device"
        ),
        modes={
            name: _parse_mode_range(value, f"{modes_path}.{name}")
            for name, value in modes_obj.items()
        },
        settings=_parse_settings(
            _as_object(obj.get("settings"), f"{path}.settings"), f"{path}.settings"
        ),
    )


def _parse_mode_range(data: object, path: str) -> ModeRange:
    obj = _as_object(data, path)
    return ModeRange(
        temperatures=tuple(
            TemperatureOption(value=_numeric_str(raw, f"{path}.temp"), raw=raw)
            for raw in _non_empty_strs(obj, "temp", path)
        ),
        air_volumes=_non_empty_strs(obj, "vol", path),
        air_directions=_non_empty_strs(obj, "dir", path),
    )


def _parse_settings(obj: JSONObject, path: str) -> AirconSettings:
    return AirconSettings(
        mode=_str(obj, "mode", path),
        temperature=_optional_temperature(_str(obj, "temp", path)),
        air_volume=_str(obj, "vol", path),
        air_direction=_str(obj, "dir", path),
        button=_str(obj, "button", path),
    )


def _optional_temperature(raw: str) -> float | None:
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _numeric_str(raw: str, path: str) -> float:
    value = _optional_temperature(raw)
    if value is None:
        raise NatureRemoResponseError(f"{path}: 数値ではない温度 {raw!r}")
    return value


def _non_empty_strs(obj: JSONObject, key: str, path: str) -> tuple[str, ...]:
    """nullableな文字列配列を読み、空文字を除く。nullは空として扱う（仕様でnullable）。"""
    value = obj.get(key)
    if value is None:
        return ()
    items = _as_list(value, f"{path}.{key}")
    result: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise NatureRemoResponseError(
                f"{path}.{key}[{index}]: 文字列ではありません"
            )
        if item:
            result.append(item)
    return tuple(result)


def _as_object(value: object, path: str) -> JSONObject:
    if not isinstance(value, dict):
        raise NatureRemoResponseError(f"{path}: オブジェクトではありません")
    return cast(JSONObject, value)


def _as_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise NatureRemoResponseError(f"{path}: 配列ではありません")
    return cast(list[object], value)


def _str(obj: JSONObject, key: str, path: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise NatureRemoResponseError(f"{path}.{key}: 文字列ではありません")
    return value


def _number(value: object, path: str) -> float:
    # boolはintのサブクラスなので明示的に除く
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise NatureRemoResponseError(f"{path}: 数値ではありません")
    return value
