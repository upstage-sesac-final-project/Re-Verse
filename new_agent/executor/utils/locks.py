"""게임 단위 asyncio 락.

같은 game_id 에 대한 동시 write 충돌을 방지한다 (단일 프로세스 내).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

game_locks: defaultdict[str, asyncio.Lock] = defaultdict(lambda: asyncio.Lock())
