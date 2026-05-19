"""UserTokenQuota — 单用户单日 LLM token 用量聚合表。

主键 (user_id, usage_date) 保证同一用户同一天只有一行；用 INSERT-OR-UPDATE
（PostgreSQL 用 ON CONFLICT，SQLite 测试环境用应用层查询合并）累加。
"""

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserTokenQuota(Base):
    __tablename__ = "user_token_quota"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True,
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "usage_date", name="user_token_quota_pkey"),
    )
