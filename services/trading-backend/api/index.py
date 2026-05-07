from fastapi import FastAPI


try:
    from src.main import app
except Exception as exc:
    app = FastAPI(title="ClashX Trading Backend")
    _startup_error = f"{exc.__class__.__name__}: {exc}"

    @app.get("/")
    async def root() -> dict[str, object]:
        return {"status": "error", "detail": "Backend failed to boot", "error": _startup_error}

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"status": "error", "detail": "Backend failed to boot", "error": _startup_error}
