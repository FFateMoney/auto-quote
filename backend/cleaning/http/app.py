from __future__ import annotations

from fastapi import FastAPI
from backend.cleaning.http.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Cleaning Service API", version="1.0.0")
    app.include_router(router)
    return app


app = create_app()
