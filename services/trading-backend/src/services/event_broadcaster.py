import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError

logger = logging.getLogger(__name__)
STREAM_EVENTS_TABLE = "stream_events"
STREAM_POLL_INTERVAL_SECONDS = 1.5
STREAM_HEARTBEAT_SECONDS = 15.0
STREAM_EVENT_FETCH_LIMIT = 100
STREAM_EVENT_RETENTION_HOURS = 24
STREAM_EVENT_CLEANUP_INTERVAL = 500
_shared_supabase: SupabaseRestClient | None = None


class EventBroadcaster:
    def __init__(self) -> None:
        self._channels: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)
        self._supabase: SupabaseRestClient | None = None
        self._persisted_events_count = 0

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
        await asyncio.to_thread(self._persist_event, channel, event, payload)

    def _persist_event(self, channel: str, event: str, payload: dict[str, Any]) -> None:
        try:
            self._get_supabase().insert(
                STREAM_EVENTS_TABLE,
                {
                    "channel": channel,
                    "event_name": event,
                    "payload_json": payload,
                },
                returning="minimal",
            )
            self._persisted_events_count += 1
            if self._persisted_events_count % STREAM_EVENT_CLEANUP_INTERVAL == 0:
                cutoff = datetime.now(UTC) - timedelta(hours=STREAM_EVENT_RETENTION_HOURS)
                self._get_supabase().delete(STREAM_EVENTS_TABLE, filters={"created_at": ("lt", cutoff.isoformat())})
        except SupabaseRestError as exc:
            logger.warning("Failed to persist stream event %s on %s: %s", event, channel, exc)

    def _get_supabase(self) -> SupabaseRestClient:
        if self._supabase is None:
            self._supabase = SupabaseRestClient()
        return self._supabase


async def queue_to_stream(queue: asyncio.Queue[str]) -> AsyncIterator[str]:
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=15)
            yield item
        except TimeoutError:
            yield format_sse(event="heartbeat", data={"ok": True})


async def channel_to_stream(channel: str, last_event_id: str | None = None) -> AsyncIterator[str]:
    last_sequence = _parse_last_event_id(last_event_id)
    if last_sequence is None:
        last_sequence = await asyncio.to_thread(_get_latest_event_sequence, channel)
    last_heartbeat_at = asyncio.get_running_loop().time()

    while True:
        rows = await asyncio.to_thread(_fetch_events_after, channel, last_sequence)
        if rows:
            for row in rows:
                sequence = row.get("event_sequence")
                event_name = row.get("event_name")
                payload = row.get("payload_json")
                if not isinstance(sequence, int) or not isinstance(event_name, str) or not isinstance(payload, dict):
                    continue
                last_sequence = sequence
                yield format_sse(event=event_name, data=payload, event_id=str(sequence))
            last_heartbeat_at = asyncio.get_running_loop().time()
            continue

        now = asyncio.get_running_loop().time()
        if (now - last_heartbeat_at) >= STREAM_HEARTBEAT_SECONDS:
            last_heartbeat_at = now
            yield format_sse(event="heartbeat", data={"ok": True})
        await asyncio.sleep(STREAM_POLL_INTERVAL_SECONDS)


def format_sse(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id else ""
    return f"{prefix}event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _parse_last_event_id(last_event_id: str | None) -> int | None:
    if not last_event_id:
        return None
    try:
        value = int(last_event_id)
    except ValueError:
        return None
    return value if value >= 0 else None


def _get_latest_event_sequence(channel: str) -> int:
    rows = _get_shared_supabase().select(
        STREAM_EVENTS_TABLE,
        columns="event_sequence",
        filters={"channel": channel},
        order="event_sequence.desc",
        limit=1,
        cache_ttl_seconds=0,
    )
    if not rows:
        return 0
    sequence = rows[0].get("event_sequence")
    return sequence if isinstance(sequence, int) else 0


def _fetch_events_after(channel: str, event_sequence: int) -> list[dict[str, Any]]:
    return _get_shared_supabase().select(
        STREAM_EVENTS_TABLE,
        columns="event_sequence,event_name,payload_json",
        filters={"channel": channel, "event_sequence": ("gt", event_sequence)},
        order="event_sequence.asc",
        limit=STREAM_EVENT_FETCH_LIMIT,
        cache_ttl_seconds=0,
    )


def _get_shared_supabase() -> SupabaseRestClient:
    global _shared_supabase
    if _shared_supabase is None:
        _shared_supabase = SupabaseRestClient()
    return _shared_supabase


broadcaster = EventBroadcaster()
