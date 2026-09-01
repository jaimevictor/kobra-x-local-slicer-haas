from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import Settings
from app.core.service import AppService
from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = Settings.load()
    app.state.service = AppService(app.state.settings)
    app.state.integration_error = None
    if app.state.settings.ha_device_id:
        # Recovery is observation-only. A missing/incompatible integration remains
        # visible through the printer integration endpoint and never enables a LAN poller.
        try:
            await app.state.service.start()
        except Exception as exc:
            app.state.integration_error = str(exc)
    yield
    await app.state.service.close()


app = FastAPI(title="Kobra X Local Slicer", lifespan=lifespan)
app.include_router(router, prefix="/api")
root = Path(__file__).parent
app.mount("/static", StaticFiles(directory=root / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(root / "templates" / "index.html")
