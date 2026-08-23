"""1 Hz telemetry for the HUD strip."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from server.chat.live import LiveRuns
from server.hardware import probe
from server.models.hud import HudSample

INTERVAL_S = 1.0


def sample(live: LiveRuns) -> HudSample:
    import psutil

    gpus, _ = probe.probe_gpus()
    memory = psutil.virtual_memory()
    return HudSample(
        gpu=gpus[0] if gpus else None,
        ram_used_mb=(memory.total - memory.available) // (1024 * 1024),
        ram_total_mb=memory.total // (1024 * 1024),
        active_runs=len(live.active_ids()),
    )


async def stream(live: LiveRuns) -> AsyncIterator[dict[str, str]]:
    while True:
        yield {"event": "hud", "data": sample(live).model_dump_json()}
        await asyncio.sleep(INTERVAL_S)
