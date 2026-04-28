"""
FastAPI application entry point.
Run with: uvicorn app.main:app --reload
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import auth, chat, history, pay, quiz, result, start, unlock, ws_chat
from app.database import create_tables
from app.limiter import limiter
from app.services.session_store import cleanup_expired_sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    mode = "DEV" if os.environ.get("DEV_MODE", "").lower() == "true" else "PROD"
    logger.info("启动中 [%s mode] — 初始化数据库表...", mode)
    create_tables()
    removed = cleanup_expired_sessions()
    logger.info("数据库就绪，清理过期 session %d 个，服务启动完成", removed)
    yield


app = FastAPI(title="Love Profiler API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(start.router)
app.include_router(chat.router)
app.include_router(result.router)
app.include_router(pay.router)
app.include_router(unlock.router)
app.include_router(ws_chat.router)
app.include_router(history.router)
app.include_router(quiz.router)

if os.environ.get("DEV_MODE", "").lower() == "true":
    from app.api import dev_auth, dev_pay
    app.include_router(dev_auth.router)
    app.include_router(dev_pay.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
