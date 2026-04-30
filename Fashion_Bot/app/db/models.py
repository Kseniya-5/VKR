import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
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

    photos = relationship(
        "UserPhoto",
        back_populates="user",
        passive_deletes=True,
    )

    outfits = relationship(
        "Outfit",
        back_populates="user",
        passive_deletes=True,
    )

    recommendations = relationship(
        "Recommendation",
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


class UserPhoto(Base):
    __tablename__ = "user_photos"
    __table_args__ = (
        CheckConstraint(
            "source IN ('telegram', 'web')",
            name="ck_user_photos_source",
        ),
        CheckConstraint(
            "processing_status IN ('uploaded', 'processing', 'ready', 'failed')",
            name="ck_user_photos_processing_status",
        ),
        Index("idx_user_photos_user_id", "user_id"),
        Index("idx_user_photos_item_type", "item_type"),
        Index("idx_user_photos_category", "category"),
        Index("idx_user_photos_processing_status", "processing_status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    source = Column(String(20), nullable=False)
    telegram_file_id = Column(Text, nullable=True)
    telegram_file_unique_id = Column(Text, nullable=True)

    original_path = Column(Text, nullable=True)
    processed_path = Column(Text, nullable=True)
    preview_path = Column(Text, nullable=True)

    mime_type = Column(String(100), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    item_type = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)
    subcategory = Column(String(100), nullable=True)
    color = Column(String(100), nullable=True)
    season = Column(String(50), nullable=True)
    style = Column(String(100), nullable=True)
    brand = Column(String(255), nullable=True)

    tags = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    is_favorite = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    processing_status = Column(String(50), nullable=False, default="uploaded")

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="photos")

    processing_jobs = relationship(
        "PhotoProcessingJob",
        back_populates="photo",
        passive_deletes=True,
    )

    outfit_items = relationship(
        "OutfitItem",
        back_populates="photo",
        passive_deletes=True,
    )


class PhotoProcessingJob(Base):
    __tablename__ = "photo_processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('background_removal', 'classification', 'embedding', 'other')",
            name="ck_photo_processing_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'done', 'failed')",
            name="ck_photo_processing_jobs_status",
        ),
        Index("idx_photo_processing_jobs_photo_id", "photo_id"),
        Index("idx_photo_processing_jobs_status", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    photo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_photos.id", ondelete="CASCADE"),
        nullable=False,
    )

    task_id = Column(String(255), nullable=True)
    job_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="pending")

    result_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    photo = relationship("UserPhoto", back_populates="processing_jobs")


class Outfit(Base):
    __tablename__ = "outfits"
    __table_args__ = (
        CheckConstraint(
            "generated_by IN ('user', 'system')",
            name="ck_outfits_generated_by",
        ),
        Index("idx_outfits_user_id", "user_id"),
        Index("idx_outfits_occasion", "occasion"),
        Index("idx_outfits_style", "style"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title = Column(String(255), nullable=True)
    occasion = Column(String(100), nullable=True)
    season = Column(String(50), nullable=True)
    style = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    generated_by = Column(String(20), nullable=False, default="system")

    is_favorite = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="outfits")

    items = relationship(
        "OutfitItem",
        back_populates="outfit",
        passive_deletes=True,
    )

    recommendations = relationship(
        "Recommendation",
        back_populates="outfit",
        passive_deletes=True,
    )


class OutfitItem(Base):
    __tablename__ = "outfit_items"
    __table_args__ = (
        UniqueConstraint("outfit_id", "photo_id", name="unique_outfit_photo"),
        Index("idx_outfit_items_outfit_id", "outfit_id"),
        Index("idx_outfit_items_photo_id", "photo_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    outfit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outfits.id", ondelete="CASCADE"),
        nullable=False,
    )

    photo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_photos.id", ondelete="CASCADE"),
        nullable=False,
    )

    item_role = Column(String(50), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    outfit = relationship("Outfit", back_populates="items")
    photo = relationship("UserPhoto", back_populates="outfit_items")


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "recommendation_type IN ('outfit', 'item', 'style_tip', 'color_match', 'seasonal')",
            name="ck_recommendations_type",
        ),
        CheckConstraint(
            "source IN ('system', 'ml', 'user')",
            name="ck_recommendations_source",
        ),
        CheckConstraint(
            "status IN ('active', 'archived', 'dismissed')",
            name="ck_recommendations_status",
        ),
        Index("idx_recommendations_user_id", "user_id"),
        Index("idx_recommendations_type", "recommendation_type"),
        Index("idx_recommendations_outfit_id", "outfit_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    outfit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outfits.id", ondelete="SET NULL"),
        nullable=True,
    )

    recommendation_type = Column(String(50), nullable=False)

    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)

    source = Column(String(20), nullable=False, default="system")
    status = Column(String(50), nullable=False, default="active")

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="recommendations")
    outfit = relationship("Outfit", back_populates="recommendations")