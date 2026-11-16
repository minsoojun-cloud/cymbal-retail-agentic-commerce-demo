"""Database models for edion-spec-banner (SQLAlchemy 2.x).

Connects to the shared AlloyDB (`edion-alloydb`) or falls back to
`seed_prod.db` / local SQLite.
Preserves `mst_product` and `mst_warranty` from `edion-product-registration` and
adds `mst_product_kinohyo` and `banner_mail_log`.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Product(Base):
    """商品マスタ (`edion-product-registration` と共有する `mst_product` テーブル)。"""

    __tablename__ = "mst_product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maker_code: Mapped[str] = mapped_column(String(10))
    search_model_no: Mapped[str] = mapped_column(String(40))
    maker_model_no: Mapped[str | None] = mapped_column(String(40))
    jan_code: Mapped[str | None] = mapped_column(String(20), index=True)
    class_code: Mapped[str | None] = mapped_column(String(10), index=True)
    product_name: Mapped[str | None] = mapped_column(Text)
    maker_name: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[str | None] = mapped_column(String(10), index=True)
    product_code: Mapped[str | None] = mapped_column(String(30))
    supplier_code: Mapped[str | None] = mapped_column(String(12))
    master_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    header_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_request_id: Mapped[str | None] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )
    updated_by: Mapped[str | None] = mapped_column(Text)

    warranties: Mapped[list[Warranty]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="Warranty.id",
    )

    __table_args__ = (
        UniqueConstraint("maker_code", "search_model_no", name="uq_mst_product_key"),
        Index("ix_mst_product_model", "search_model_no"),
    )


class Warranty(Base):
    """長期(01) / 安心(07) / 延長(03) 保証マスタ (`mst_warranty`)。"""

    __tablename__ = "mst_warranty"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("mst_product.id"), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    product: Mapped[Product] = relationship(back_populates="warranties")


class ProductKinohyo(Base):
    """カテゴリ別 機能表詳細スペック (`mst_product_kinohyo`)。"""

    __tablename__ = "mst_product_kinohyo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("mst_product.id", ondelete="SET NULL"), index=True, nullable=True
    )
    jan_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    search_model_no: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(
        String(30), index=True
    )  # tv | pc | wine_cellar | cooler_warmer | freezer | refrigerator
    template_variant: Mapped[str] = mapped_column(String(40), default="auto")
    specs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ai_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class BannerMailLog(Base):
    """バナー添付メール送信・リレーキュー履歴 (`banner_mail_log`)。"""

    __tablename__ = "banner_mail_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    jan_code: Mapped[str | None] = mapped_column(String(20), index=True)
    search_model_no: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(30))
    to_email: Mapped[str] = mapped_column(Text)
    cc_email: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    attachment_format: Mapped[str] = mapped_column(String(20), default="both")  # jpeg | pdf | both
    status: Mapped[str] = mapped_column(
        String(30), index=True, default="SENT"
    )  # SENT | QUEUED | RELAYED | FAILED
    delivery_method: Mapped[str] = mapped_column(
        String(40), default="gmail_cli"
    )  # gmail_cli | smtp | relay_queue
    jpeg_uri: Mapped[str | None] = mapped_column(Text)
    pdf_uri: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BannerTemplate(Base):
    """カテゴリ別カスタムテンプレート＆項目配置定義 (`mst_banner_template`)。
    商品マスタ (`mst_product`) は一切変更せず、本ツール専用の動的テンプレート定義を保持する。
    """

    __tablename__ = "mst_banner_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40), index=True)
    orientation: Mapped[str] = mapped_column(String(20), default="landscape")
    is_preset: Mapped[int] = mapped_column(Integer, default=0)
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_image_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


def resolve_database_url(explicit_url: str | None = None) -> str:
    if explicit_url:
        return explicit_url
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    local_sqlite = os.path.abspath("./data/cymbal_banner.db")
    os.makedirs(os.path.dirname(local_sqlite), exist_ok=True)
    return f"sqlite:///{local_sqlite}"


def make_engine(url: str | None = None):
    resolved = resolve_database_url(url)
    kwargs: dict[str, Any] = {}
    if resolved.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(resolved, **kwargs)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
