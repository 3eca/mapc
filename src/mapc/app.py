from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from mapc.auth import AuthStore, guard
from mapc.auth import router as authrouter
from mapc.db import build_engine, init_db
from mapc.routes.cameras import router as camrouter
from mapc.routes.maps import router as maprouter
from mapc.routes.scans import router as scanrouter
from mapc.services.scan_manager import ScanManager
from mapc.services.snapshot import SnapshotService
from mapc.settings import AppSettings, ScanConfig

appsettings = AppSettings()
scancfg = ScanConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = build_engine(appsettings)
    manager = ScanManager(appsettings, scancfg)
    snapshots = SnapshotService(appsettings)

    try:
        init_db(engine)
        app.state.engine = engine
        app.state.scan_manager = manager
        app.state.snapshots = snapshots
        yield
    finally:
        try:
            await snapshots.close()
            await manager.close()
        finally:
            engine.dispose()


app = FastAPI(lifespan=lifespan, title="mapc")
app.state.auth = AuthStore(appsettings)
app.middleware("http")(guard)
app.include_router(authrouter)
app.include_router(camrouter)
app.include_router(scanrouter)
app.include_router(maprouter)

# Public bundle assets contain no camera data; API routes retain session protection.
frontend_dir = Path(__file__).parent / "static" / "app"
app.mount("/ui", StaticFiles(directory=frontend_dir, check_dir=False), name="ui")


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(frontend_dir / "index.html")


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(frontend_dir / "index.html")


@app.get("/health", include_in_schema=False)
def health(request: Request):
    with request.app.state.engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
