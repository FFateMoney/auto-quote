from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.common.auth import SinglePasswordAuthMiddleware
from backend.common.logging import setup_logging
from backend.quote.http.routes import router


setup_logging()

app = FastAPI(title="Auto Quote Service", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SinglePasswordAuthMiddleware,
    exempt_paths={
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/session",
        "/api/health",
    },
)
app.include_router(router)
