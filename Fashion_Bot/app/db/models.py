import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    web_accounts = relationship("WebAccount", back_populates="user")


class WebAccount(Base):
    __tablename__ = "web_accounts"
    __table_args__ = (
        UniqueConstraint("email", name="uq_web_accounts_email"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="web_accounts")