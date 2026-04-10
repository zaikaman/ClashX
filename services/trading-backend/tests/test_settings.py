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
