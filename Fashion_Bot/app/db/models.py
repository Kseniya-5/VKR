import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    web_account = relationship(
        "WebAccount",
        back_populates="user",
        uselist=False,
        passive_deletes=True,
    )

    telegram_account = relationship(
        "TelegramAccount",
        back_populates="user",
        uselist=False,
        passive_deletes=True,
    )

    account_link_codes = relationship(
        "AccountLinkCode",
        back_populates="user",
        passive_deletes=True,
    )

    model_tasks = relationship(
        "ModelTask",
        back_populates="user",
        passive_deletes=True,
    )


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_telegram_accounts_user_id"),
    )

    telegram_id = Column(BigInteger, primary_key=True)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="telegram_account")


class WebAccount(Base):
    __tablename__ = "web_accounts"
    __table_args__ = (
        UniqueConstraint("email", name="uq_web_accounts_email"),
        UniqueConstraint("user_id", name="uq_web_accounts_user_id"),
        CheckConstraint(
            r"email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'",
            name="valid_email",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="web_account")


class AccountLinkCode(Base):
    __tablename__ = "account_link_codes"

    code = Column(String(10), primary_key=True)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="account_link_codes")


class ModelTask(Base):
    __tablename__ = "model_tasks"

    task_id = Column(String(255), primary_key=True)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    status = Column(String(50), nullable=False)
    result = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="model_tasks")