"""
Payment API — ByteDance mini-program payment integration.
POST /pay/create_order  { assessment_id: int }  →  { out_trade_no: str, order_info: dict }
POST /pay/callback      (ByteDance async notification)
POST /pay/query         { out_trade_no: str }   →  { status: str }
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.limiter import limiter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.models.order import Order

router = APIRouter(prefix="/pay", tags=["pay"])

ASSESSMENT_PRICE_FEN = 990  # ¥9.90 in fen
_CREATE_ORDER_URL = "https://developer.toutiao.com/api/apps/ecpay/v1/create_order"


class CreateOrderRequest(BaseModel):
    assessment_id: int


class CreateOrderResponse(BaseModel):
    out_trade_no: str
    order_info: dict


class QueryRequest(BaseModel):
    out_trade_no: str


class QueryResponse(BaseModel):
    status: str


@router.post("/create_order", response_model=CreateOrderResponse)
@limiter.limit("5/minute")
async def create_order(
    request: Request,
    body: CreateOrderRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CreateOrderResponse:
    """Create a payment order with ByteDance and persist it locally."""
    assessment = (
        db.query(Assessment)
        .filter(Assessment.id == body.assessment_id, Assessment.user_id == user_id)
        .first()
    )
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    out_trade_no = f"LP{uuid.uuid4().hex[:20].upper()}"

    app_id = settings.douyin_app_id
    app_secret = settings.douyin_app_secret

    payload = {
        "app_id": app_id,
        "out_trade_no": out_trade_no,
        "total_amount": ASSESSMENT_PRICE_FEN,
        "subject": "恋爱人格测评报告",
        "body": "解锁您的专属恋爱人格分析报告",
        "valid_time": 3600,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _CREATE_ORDER_URL,
                json={"secret": app_secret, **payload},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Payment API error") from exc

    order_info = resp.json()

    order = Order(
        user_id=user_id,
        assessment_id=assessment.id,
        out_trade_no=out_trade_no,
        amount=ASSESSMENT_PRICE_FEN,
        status="pending",
    )
    db.add(order)
    db.commit()

    logger.info("[/pay/create_order] user_id=%s assessment_id=%s out_trade_no=%s amount=%s分", user_id, body.assessment_id, out_trade_no, ASSESSMENT_PRICE_FEN)
    return CreateOrderResponse(out_trade_no=out_trade_no, order_info=order_info)


@router.post("/callback")
@limiter.limit("10/minute")
async def payment_callback(request: Request, db: Session = Depends(get_db)):
    """Receive ByteDance async payment notification and mark order as paid."""
    body_bytes = await request.body()

    # Verify HMAC signature from ByteDance (fail-closed: 缺 token 直接拒绝)
    token = settings.douyin_pay_token
    if not token:
        if settings.dev_mode:
            logger.warning("[/pay/callback] DEV_MODE: 跳过验签")
        else:
            logger.error("[/pay/callback] DOUYIN_PAY_TOKEN 未配置，拒绝回调（fail-closed）")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signature verification not configured")

    if token:
        timestamp = request.headers.get("timestamp", "")
        nonce = request.headers.get("nonce", "")
        signature = request.headers.get("msg_signature", "")
        items = sorted([token, timestamp, nonce, body_bytes.decode()])
        expected = hashlib.sha256("".join(items).encode()).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    try:
        data = json.loads(body_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc

    out_trade_no = data.get("out_trade_no")
    pay_status = data.get("status")  # "PAY_SUCCESS" etc.

    logger.info("[/pay/callback] out_trade_no=%s pay_status=%s", out_trade_no, pay_status)
    if out_trade_no and pay_status == "PAY_SUCCESS":
        order = db.query(Order).filter(Order.out_trade_no == out_trade_no).first()
        if order and order.status == "pending":
            callback_amount = data.get("total_amount")
            if callback_amount is not None and int(callback_amount) != order.amount:
                logger.error("[/pay/callback] 金额不匹配 order=%s回调=%s out_trade_no=%s",
                             order.amount, callback_amount, out_trade_no)
                return {"message": "amount mismatch"}
            order.status = "paid"
            db.commit()
            logger.info("[/pay/callback] 订单已标记为已支付 out_trade_no=%s", out_trade_no)

    return {"message": "ok"}


@router.post("/query", response_model=QueryResponse)
@limiter.limit("10/minute")
async def query_order(
    request: Request,
    body: QueryRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> QueryResponse:
    """Return the current status of an order."""
    order = (
        db.query(Order)
        .filter(Order.out_trade_no == body.out_trade_no, Order.user_id == user_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return QueryResponse(status=order.status)
