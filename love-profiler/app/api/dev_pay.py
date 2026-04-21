"""
Dev-only payment simulation — 仅在 DEV_MODE=true 时可用。
POST /dev/pay-success?out_trade_no=xxx  →  { status: "paid" }

用途：本地测试时绕过字节跳动支付回调，直接将订单置为已支付。
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import Order

router = APIRouter(prefix="/dev", tags=["dev"])
logger = logging.getLogger(__name__)


@router.post("/pay-success")
def dev_pay_success(out_trade_no: str, db: Session = Depends(get_db)) -> dict:
    """将指定订单直接置为已支付（DEV_MODE 专用）。"""
    if os.environ.get("DEV_MODE", "").lower() != "true":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    order = db.query(Order).filter(Order.out_trade_no == out_trade_no).first()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order.status = "paid"
    db.commit()
    logger.info("[/dev/pay-success] 订单已模拟支付 out_trade_no=%s", out_trade_no)
    return {"status": "paid", "out_trade_no": out_trade_no}
