"""定数。"""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "nature_remo"
MANUFACTURER: Final = "Nature"

# Nature APIの制限は5分あたり30リクエスト。1回の更新で2リクエストなので5分で10回になる
UPDATE_INTERVAL: Final = timedelta(seconds=60)
