import asyncio

from src.services.creator_marketplace_service import CreatorMarketplaceService


class _FakeSupabase:
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

    async def _fake_build_creator_profile_live(*, creator_id: str):
        assert creator_id == "creator-1"
        return expected

    monkeypatch.setattr(service, "_build_creator_profile_live", _fake_build_creator_profile_live)

    payload = asyncio.run(service.get_creator_profile(creator_id="creator-1"))

    assert payload == expected
