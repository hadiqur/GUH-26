"""Dial-a-Text FastAPI app. Routers are added here by each feature."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Dial-a-Text", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
