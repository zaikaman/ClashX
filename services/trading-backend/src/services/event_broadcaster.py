import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any


class EventBroadcaster:
    def __init__(self) -> None:
        self._channels: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)

    def subscribe(self, channel: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._channels[channel].add(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue[str]) -> None:
        listeners = self._channels.get(channel)
        if not listeners:
            return
        listeners.discard(queue)
        if not listeners:
            self._channels.pop(channel, None)

    async def publish(self, channel: str, event: str, payload: dict[str, Any]) -> None:
        message = format_sse(event=event, data=payload)
        for queue in tuple(self._channels.get(channel, set())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Drop when a subscriber is slow to preserve broadcaster throughput.
                continue


async def queue_to_stream(queue: asyncio.Queue[str]) -> AsyncIterator[str]:
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=15)
            yield item
        except TimeoutError:
            yield format_sse(event="heartbeat", data={"ok": True})


def format_sse(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id else ""
    return f"{prefix}event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


broadcaster = EventBroadcaster()
