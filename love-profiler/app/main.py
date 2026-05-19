"""
FastAPI application entry point.
Run with: uvicorn app.main:app --reload
"""

import logging
import logging.handlers
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

# File handler: rotate at 10 MB, keep 5 backups
_log_dir = "logs"
os.makedirs(_log_dir, exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(_log_dir, "app.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().addHandler(_file_handler)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import admin, auth, history, pay, quiz, result, unlock, ws_result
from app.database import create_tables
from app.models import ai_call_log  # noqa: F401 — registers AiCallLog with Base
from app.models import user_token_quota  # noqa: F401 — registers UserTokenQuota
from app.models import report_quality_audit  # noqa: F401 — registers ReportQualityAudit
from app.limiter import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    mode = "DEV" if os.environ.get("DEV_MODE", "").lower() == "true" else "PROD"
    logger.info("启动中 [%s mode] — 初始化数据库表...", mode)
    create_tables()
    logger.info("数据库就绪，服务启动完成")
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

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(result.router)
app.include_router(pay.router)
app.include_router(unlock.router)
app.include_router(ws_result.router)
app.include_router(history.router)
app.include_router(quiz.router)

app.mount("/static", StaticFiles(directory="static"), name="static")

if os.environ.get("DEV_MODE", "").lower() == "true":
    from app.api import dev_auth, dev_pay
    app.include_router(dev_auth.router)
    app.include_router(dev_pay.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
