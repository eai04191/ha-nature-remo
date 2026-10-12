"""Nature APIの応答例。形はswagger.nature.globalのOpenAPI定義に合わせている。

- Living: 冷房中。上下風向が `[""]` だけの機種（実機のリビング相当）
- Study: 除湿中で設定温度が空文字。除湿は温度設定なし
- Bedroom: 電源OFF。最後のモードは暖房
- Remo nano: センサーを持たないRemo本体
"""

from typing import Any

CREATED_AT = "2026-10-12T00:00:00Z"


def _device(device_id: str, name: str) -> dict[str, Any]:
    return {
        "id": device_id,
        "name": name,
        "firmware_version": "Remo/1.14.6",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
        "mac_address": "00:00:00:00:00:00",
        "bt_mac_address": "00:00:00:00:00:01",
        "serial_number": "1W000000000000",
        "temperature_offset": 0,
        "humidity_offset": 0,
    }


def _event(val: float) -> dict[str, Any]:
    return {"val": val, "created_at": CREATED_AT}


def _temps(start: int, stop: int) -> list[str]:
    return [str(t) for t in range(start, stop + 1)]


def _mode(temp: list[str], vol: list[str], dir_: list[str]) -> dict[str, Any]:
    return {"temp": temp, "dir": dir_, "dirh": [""], "vol": vol}


def _aircon(
    appliance_id: str,
    nickname: str,
    device: dict[str, Any],
    modes: dict[str, Any],
    settings: dict[str, str],
) -> dict[str, Any]:
    return {
        "id": appliance_id,
        "type": "AC",
        "nickname": nickname,
        "image": "ico_ac_1",
        "model": None,
        "device": device,
        "signals": [],
        "aircon": {
            "tempUnit": "c",
            "range": {"modes": modes, "fixedButtons": ["power-off"]},
        },
        "settings": {
            **settings,
            "temp_unit": "c",
            "dirh": "",
            "updated_at": CREATED_AT,
        },
    }


VOLUMES = ["auto", "1", "2", "3"]

USER: dict[str, Any] = {"id": "user-1", "nickname": "eai"}

DEVICES: list[dict[str, Any]] = [
    {
        **_device("dev-living", "Living Remo"),
        "newest_events": {
            "te": _event(25.4),
            "hu": _event(48),
            "il": _event(120),
            "mo": {"val": 1, "created_at": CREATED_AT},
        },
    },
    {
        **_device("dev-study", "Study Remo"),
        "newest_events": {"te": _event(22.1), "hu": _event(55)},
    },
    {**_device("dev-nano", "Remo nano"), "newest_events": {}},
]

APPLIANCES: list[dict[str, Any]] = [
    _aircon(
        "ac-living",
        "Living",
        _device("dev-living", "Living Remo"),
        {
            "cool": _mode([*_temps(16, 30), "26.5"], VOLUMES, [""]),
            "warm": _mode(_temps(16, 30), VOLUMES, [""]),
            "dry": _mode(["-2", "-1", "0", "1", "2"], ["auto"], [""]),
            "blow": _mode([""], VOLUMES, [""]),
            "auto": _mode(["-2", "-1", "0", "1", "2"], VOLUMES, [""]),
        },
        {"mode": "cool", "temp": "26", "vol": "auto", "dir": "", "button": ""},
    ),
    _aircon(
        "ac-study",
        "Study",
        _device("dev-study", "Study Remo"),
        {
            "cool": _mode(_temps(18, 30), VOLUMES, ["auto", "1", "2", "swing"]),
            "warm": _mode(_temps(16, 30), VOLUMES, ["auto", "1", "2", "swing"]),
            "dry": _mode([""], ["auto"], ["auto", "1", "2", "swing"]),
        },
        {"mode": "dry", "temp": "", "vol": "auto", "dir": "auto", "button": ""},
    ),
    _aircon(
        "ac-bedroom",
        "Bedroom",
        _device("dev-living", "Living Remo"),
        {
            "cool": _mode(_temps(18, 30), VOLUMES, ["auto", "1"]),
            "warm": _mode(_temps(16, 30), VOLUMES, ["auto", "1"]),
        },
        {"mode": "warm", "temp": "22", "vol": "1", "dir": "1", "button": "power-off"},
    ),
    {
        "id": "light-1",
        "type": "LIGHT",
        "nickname": "Light",
        "image": "ico_light",
        "model": None,
        "device": _device("dev-living", "Living Remo"),
        "signals": [],
        "light": {"buttons": [], "state": {"brightness": "100", "power": "on"}},
    },
    {
        "id": "ir-1",
        "type": "IR",
        "nickname": "Fan",
        "image": "ico_fan",
        "model": None,
        "device": _device("dev-study", "Study Remo"),
        "signals": [{"id": "sig-1", "name": "on", "image": "ico_on"}],
    },
]
