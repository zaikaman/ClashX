import asyncio
from types import SimpleNamespace

from src.api.bot_copy import BotRuntimeProfileResponse
from src.services.creator_marketplace_service import CreatorMarketplaceService


class _FakeSupabase:
    def __init__(self) -> None:
        self.insert_calls: list[tuple[str, object, dict[str, object]]] = []

    def maybe_one(self, table: str, **_kwargs):
        if table == "marketplace_creator_snapshots":
            return {
                "profile_json": {
                    "creator_id": "creator-1",
                    "bots": [
                        {
                            "runtime_id": "runtime-1",
                            "bot_definition_id": "bot-1",
                            "bot_name": "Incomplete snapshot row",
                            "strategy_type": "trend",
                            "rank": 1,
                        }
                    ],
                }
            }
        return None

    def select(self, table: str, **_kwargs):
        if table == "marketplace_runtime_snapshots":
            return []
        return []

    def insert(self, table: str, values, **kwargs):
        self.insert_calls.append((table, values, kwargs))
        return [values] if isinstance(values, dict) else values


def test_get_creator_profile_rebuilds_when_snapshot_bots_are_incomplete(monkeypatch) -> None:
    service = CreatorMarketplaceService.__new__(CreatorMarketplaceService)
    service.supabase = _FakeSupabase()

    expected = {
        "creator_id": "creator-1",
        "bots": [
            {
                "runtime_id": "runtime-1",
                "bot_definition_id": "bot-1",
                "bot_name": "Live row",
                "strategy_type": "trend",
                "authoring_mode": "visual",
                "rank": 1,
                "pnl_total": 0.0,
                "pnl_unrealized": 0.0,
                "win_streak": 0,
                "drawdown": 0.0,
                "captured_at": "2026-04-12T17:18:23.679912+00:00",
                "trust": {},
                "drift": {},
                "passport": {},
                "creator": {},
                "copy_stats": {"mirror_count": 0, "active_mirror_count": 0, "clone_count": 0},
                "publishing": {
                    "visibility": "public",
                    "access_mode": "public",
                    "publish_state": "published",
                    "hero_headline": "",
                    "access_note": "",
                    "featured_collection_title": None,
                    "featured_rank": 0,
                    "is_featured": False,
                    "invite_count": 0,
                },
            }
        ],
        "featured_bots": [],
    }

    async def _fake_build_creator_profile_live(*, creator_id: str, public_rows=None):
        assert creator_id == "creator-1"
        assert public_rows is None
        return expected

    monkeypatch.setattr(service, "_build_creator_profile_live", _fake_build_creator_profile_live)

    payload = asyncio.run(service.get_creator_profile(creator_id="creator-1"))

    assert payload == expected
    assert len(service.supabase.insert_calls) == 1
    insert_table, insert_values, insert_kwargs = service.supabase.insert_calls[0]
    assert insert_table == "marketplace_creator_snapshots"
    assert insert_kwargs["upsert"] is True
    assert insert_kwargs["on_conflict"] == "creator_id"
    assert isinstance(insert_values, dict)
    assert insert_values["creator_id"] == "creator-1"
    assert insert_values["profile_json"] == expected


def test_runtime_profile_normalizes_creator_bots_to_summary_shape() -> None:
    service = CreatorMarketplaceService.__new__(CreatorMarketplaceService)

    payload = service._normalize_runtime_profile_payload(
        {
            "runtime_id": "runtime-1",
            "bot_definition_id": "bot-1",
            "bot_name": "Bot",
            "description": "",
            "strategy_type": "trend",
            "authoring_mode": "visual",
            "status": "active",
            "mode": "live",
            "risk_policy_json": {},
            "rank": 1,
            "pnl_total": 0.0,
            "pnl_unrealized": 0.0,
            "win_streak": 0,
            "drawdown": 0.0,
            "recent_events": [],
            "trust": {
                "trust_score": 80,
                "uptime_pct": 99.0,
                "failure_rate_pct": 0.0,
                "health": "healthy",
                "heartbeat_age_seconds": 0,
                "risk_grade": "A",
                "risk_score": 80,
                "summary": "",
                "badges": [],
            },
            "drift": {
                "status": "aligned",
                "score": 50,
                "summary": "",
                "live_pnl_pct": None,
                "benchmark_pnl_pct": None,
                "return_gap_pct": None,
                "live_drawdown_pct": 0.0,
                "benchmark_drawdown_pct": None,
                "drawdown_gap_pct": None,
                "benchmark_run_id": None,
                "benchmark_completed_at": None,
            },
            "passport": {
                "market_scope": "Pacifica perpetuals",
                "strategy_type": "trend",
                "authoring_mode": "visual",
                "rules_version": 1,
                "current_version": 1,
                "release_count": 1,
                "public_since": None,
                "last_published_at": None,
                "latest_backtest_at": None,
                "latest_backtest_run_id": None,
                "version_history": [],
                "publish_history": [],
            },
            "creator": {
                "creator_id": "creator-1",
                "wallet_address": "wallet-1",
                "display_name": "Creator",
                "public_bot_count": 1,
                "active_runtime_count": 1,
                "mirror_count": 0,
                "active_mirror_count": 0,
                "clone_count": 0,
                "average_trust_score": 80,
                "best_rank": 1,
                "reputation_score": 80,
                "reputation_label": "trusted",
                "summary": "",
                "tags": [],
                "bots": [
                    {
                        "runtime_id": "runtime-1",
                        "bot_definition_id": "bot-1",
                        "bot_name": "Bot",
                        "strategy_type": "trend",
                        "authoring_mode": "visual",
                        "rank": 1,
                        "pnl_total": 0.0,
                        "pnl_unrealized": 0.0,
                        "win_streak": 0,
                        "drawdown": 0.0,
                        "captured_at": "2026-04-12T17:18:23.679912+00:00",
                        "trust": {"trust_score": 80, "risk_grade": "A"},
                        "drift": {"status": "aligned"},
                        "passport": {},
                        "creator": {},
                        "copy_stats": {"mirror_count": 0, "active_mirror_count": 0, "clone_count": 0},
                        "publishing": {
                            "visibility": "public",
                            "access_mode": "public",
                            "publish_state": "published",
                            "hero_headline": "",
                            "access_note": "",
                            "featured_collection_title": None,
                            "featured_rank": 0,
                            "is_featured": False,
                            "invite_count": 0,
                        },
                    }
                ],
            },
        }
    )

    model = BotRuntimeProfileResponse.model_validate(payload)

    assert model.creator.bots[0].trust_score == 80
    assert model.creator.bots[0].risk_grade == "A"
    assert model.creator.bots[0].drift_status == "aligned"


def test_refresh_after_publication_refreshes_leaderboard_then_snapshots(monkeypatch) -> None:
    service = CreatorMarketplaceService.__new__(CreatorMarketplaceService)
    calls: list[tuple[str, int | None]] = []

    async def _fake_refresh_public_leaderboard(_db, *, limit: int):
        calls.append(("leaderboard", limit))

    async def _fake_refresh_public_snapshots(*, limit: int = 120):
        calls.append(("snapshots", limit))

    monkeypatch.setattr(
        service,
        "leaderboard_engine",
        SimpleNamespace(refresh_public_leaderboard=_fake_refresh_public_leaderboard),
        raising=False,
    )
    monkeypatch.setattr(service, "refresh_public_snapshots", _fake_refresh_public_snapshots, raising=False)
    monkeypatch.setattr(service, "_clear_marketplace_cache", lambda: calls.append(("clear", None)), raising=False)

    asyncio.run(service.refresh_after_publication(limit=75))

    assert calls == [
        ("leaderboard", 120),
        ("clear", None),
        ("snapshots", 120),
    ]
