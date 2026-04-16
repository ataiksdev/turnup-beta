from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.router import router
import os

os.makedirs("data", exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Turnup Auth Service", version="1.0.0", lifespan=lifespan,
              docs_url="/docs", openapi_url="/openapi.json")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(router)


@app.get("/health")
async def health():
    return {"service": "auth", "status": "ok"}
