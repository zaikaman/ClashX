import src.core.settings as settings_module


def test_get_settings_defaults_include_localhost_and_production_origin(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://supabase.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.cors_allowed_origins == (
        "http://localhost:3000",
        "https://clash-x.vercel.app",
    )
    settings_module.get_settings.cache_clear()


def test_get_settings_normalizes_configured_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://supabase.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        " https://clash-x.vercel.app/ , http://localhost:3000 , https://clash-x.vercel.app ",
    )
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.cors_allowed_origins == (
        "https://clash-x.vercel.app",
        "http://localhost:3000",
    )
    settings_module.get_settings.cache_clear()


def test_get_settings_applies_free_tier_runtime_floors(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://supabase.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("PACIFICA_SNAPSHOT_CACHE_TTL_SECONDS", "2")
    monkeypatch.setenv("PACIFICA_FAST_EVALUATION_SECONDS", "5")
    monkeypatch.setenv("PACIFICA_ACTIVE_WALLET_POLL_SECONDS", "4")
    monkeypatch.setenv("PACIFICA_WARM_WALLET_POLL_SECONDS", "15")
    monkeypatch.setenv("PACIFICA_IDLE_WALLET_POLL_SECONDS", "45")
    monkeypatch.setenv("PACIFICA_PERFORMANCE_REFRESH_SECONDS", "60")
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.pacifica_snapshot_cache_ttl_seconds == 15
    assert settings.pacifica_fast_evaluation_seconds == 15
    assert settings.pacifica_active_wallet_poll_seconds == 15
    assert settings.pacifica_warm_wallet_poll_seconds == 60
    assert settings.pacifica_idle_wallet_poll_seconds == 180
    assert settings.pacifica_performance_refresh_seconds == 180
    settings_module.get_settings.cache_clear()
