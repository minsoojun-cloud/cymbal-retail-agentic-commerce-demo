"""FastAPI Backend for EDION VMD 機能表・POP自動生成スタジオ (`edion-spec-banner`)."""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from edion_banner.ai_spec_enricher import enrich_specs_with_gemini
from edion_banner.category_schemas import (
    CATEGORY_DEFINITIONS,
    DOOR_LAYOUT_MAP,
    default_specs_for_category,
    infer_category_from_product,
)
from edion_banner.default_dynamic_templates import PRESET_TEMPLATES, get_default_templates
from edion_banner.excel_importer import parse_kinohyo_excel
from edion_banner.mailer import send_banner_email
from edion_banner.models import (
    BannerMailLog,
    BannerTemplate,
    Base,
    Product,
    ProductKinohyo,
    make_engine,
    make_session_factory,
    now_utc,
    resolve_database_url,
)
from edion_banner.renderer import (
    _encode_image_to_jpeg,
    _encode_image_to_pdf,
    generate_jpeg_bytes_async,
    generate_pdf_bytes_async,
    persist_banner_artifact,
    persist_banner_to_bigquery,
    resolve_banner_image_async,
)
from edion_banner.seed_data import seed_kinohyo_specs, upsert_master_and_kinohyo
from edion_banner.template_vision import analyze_banner_image_with_gemini


class UpdateSpecsPayload(BaseModel):
    category: str | None = None
    template_variant: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    image_data_url: str | None = None
    edion_price: int | str | None = None
    product_name: str | None = None
    maker_name: str | None = None


class CreateProductPayload(BaseModel):
    category: str = "tv"
    jan_code: str
    search_model_no: str
    maker_name: str = ""
    product_name: str = ""
    class_code: str = "11000000"
    edion_price: int = 98000
    long_warranty: str = "60"
    features: str = ""
    specs: dict[str, Any] = Field(default_factory=dict)


class ExportBannerPayload(BaseModel):
    product_id: int | str | None = None
    jan_code: str | None = None
    category: str = "tv"
    specs: dict[str, Any] = Field(default_factory=dict)
    image_data_url: str | None = None
    filename: str | None = None


class SendEmailPayload(BaseModel):
    to_email: str
    cc_email: str | None = None
    subject: str = "【Cymbal VMD】店舗展示用 機能表（POPバナー）送付のご案内"
    body: str = "お疲れ様です。\nCymbal Retail VMD 機能表・POP自動生成スタジオより、対象商品の機能表データを添付にてお送りいたします。"
    attachment_format: str = "both"  # jpeg | pdf | both
    product_id: int | str | None = None
    jan_code: str | None = None
    search_model_no: str | None = None
    category: str = "tv"
    specs: dict[str, Any] = Field(default_factory=dict)
    image_data_url: str | None = None


class SaveTemplatePayload(BaseModel):
    template_id: str | None = None
    name: str
    category: str = "tv"
    orientation: str = "landscape"
    status: str = "draft"  # draft (一時保存) | published (公開)
    is_category_default: bool = False  # True = make default for this category in Standard Studio
    assigned_models: list[str] = Field(default_factory=list)  # Specific search_model_no / jan_code list
    schema_json: dict[str, Any] = Field(default_factory=dict)
    image_data_url: str | None = None


def _serialize_joined_product(prod: Product | None, kino: ProductKinohyo | None) -> dict[str, Any]:
    input_data = (prod.input_data if prod and isinstance(prod.input_data, dict) else {}) or {}
    master_data = (prod.master_data if prod and isinstance(prod.master_data, dict) else {}) or {}

    jan_code = (
        (kino.jan_code if kino else None)
        or (prod.jan_code if prod else None)
        or input_data.get("jan_code")
        or ""
    )
    model_no = (
        (kino.search_model_no if kino else None)
        or (prod.search_model_no if prod else None)
        or input_data.get("edion_model_no")
        or ""
    )
    maker_name = (
        (prod.maker_name if prod else None)
        or input_data.get("maker_name")
        or (kino.specs.get("maker") if kino and isinstance(kino.specs, dict) else None)
        or ""
    )
    product_name = (
        (prod.product_name if prod else None)
        or input_data.get("product_name")
        or model_no
    )
    class_code = (prod.class_code if prod else None) or input_data.get("class_code") or ""
    features = input_data.get("features") or ""

    category = (
        (kino.category if kino else None)
        or infer_category_from_product(product_name, class_code, features, model_no)
        or "tv"
    )
    base_specs = default_specs_for_category(category)
    raw_specs = (kino.specs if kino and isinstance(kino.specs, dict) else {}) or {}
    merged_specs = {**base_specs, **raw_specs}
    if maker_name and not merged_specs.get("maker"):
        merged_specs["maker"] = maker_name
    if model_no and not merged_specs.get("model_no"):
        merged_specs["model_no"] = model_no
    if jan_code and not merged_specs.get("jan_code"):
        merged_specs["jan_code"] = jan_code

    edion_price_raw = input_data.get("edion_price") or master_data.get("edion_price") or "0"
    shikiri_price_raw = input_data.get("shikiri_price") or master_data.get("shikiri_price") or "0"
    try:
        edion_price = int(float(str(edion_price_raw).replace(",", "")))
    except Exception:
        edion_price = 0
    try:
        shikiri_price = int(float(str(shikiri_price_raw).replace(",", "")))
    except Exception:
        shikiri_price = 0

    margin_rate = round((edion_price - shikiri_price) / edion_price * 100, 1) if edion_price > 0 else 0.0

    return {
        "id": kino.id if kino else (prod.id if prod else 0),
        "kinohyo_id": kino.id if kino else None,
        "product_id": prod.id if prod else (kino.product_id if kino else None),
        "jan_code": jan_code,
        "search_model_no": model_no,
        "maker_model_no": (prod.maker_model_no if prod else model_no) or model_no,
        "maker_code": (prod.maker_code if prod else "") or "",
        "maker_name": maker_name,
        "product_name": product_name,
        "class_code": class_code,
        "category": category,
        "category_name": CATEGORY_DEFINITIONS.get(category, {}).get("name", category),
        "template_variant": kino.template_variant if kino else "auto",
        "has_kinohyo": kino is not None,
        "linked_master": prod is not None,
        "edion_price": edion_price,
        "shikiri_price": shikiri_price,
        "margin_rate": margin_rate,
        "maker_price": input_data.get("maker_price") or master_data.get("maker_price") or "オープン",
        "long_warranty": input_data.get("long_warranty") or "60",
        "features": features,
        "rec_comment_1": input_data.get("rec_comment_1") or "",
        "rec_comment_2": input_data.get("rec_comment_2") or "",
        "rec_comment_3": input_data.get("rec_comment_3") or "",
        "effective_date": (prod.effective_date if prod else None) or input_data.get("effective_date") or "",
        "specs": merged_specs,
        "ai_metadata": (kino.ai_metadata if kino and isinstance(kino.ai_metadata, dict) else {}) or {},
        "updated_at": (
            kino.updated_at.isoformat()
            if kino and kino.updated_at
            else (prod.updated_at.isoformat() if prod and prod.updated_at else None)
        ),
        "registration_url": os.environ.get("PRODUCT_REG_URL", ""),
    }


def _find_product_and_kinohyo(
    session: Session, identifier: str
) -> tuple[Product | None, ProductKinohyo | None]:
    ident = identifier.strip()
    ident_no_hyphen = ident.replace("-", "")
    prod: Product | None = None
    kino: ProductKinohyo | None = None

    # Only treat short numeric strings (< 8 digits) as 32-bit integer primary keys.
    # 8-digit or 13-digit JAN codes must NOT be queried against the 32-bit INTEGER `id` column.
    if ident.isdigit() and len(ident) < 8:
        num_id = int(ident)
        kino = session.scalar(select(ProductKinohyo).where(ProductKinohyo.id == num_id))
        if kino and kino.product_id:
            prod = session.scalar(select(Product).where(Product.id == kino.product_id))
        if not kino and not prod:
            prod = session.scalar(select(Product).where(Product.id == num_id))
            if prod:
                kino = session.scalar(
                    select(ProductKinohyo).where(
                        (ProductKinohyo.product_id == prod.id)
                        | (ProductKinohyo.jan_code == prod.jan_code)
                        | (ProductKinohyo.search_model_no == prod.search_model_no)
                    )
                )

    if not kino and not prod:
        kino = session.scalar(
            select(ProductKinohyo).where(
                (ProductKinohyo.jan_code == ident)
                | (ProductKinohyo.search_model_no == ident)
                | (ProductKinohyo.search_model_no == ident_no_hyphen)
            )
        )
        prod = session.scalar(
            select(Product).where(
                (Product.jan_code == ident)
                | (Product.search_model_no == ident)
                | (Product.search_model_no == ident_no_hyphen)
            )
        )
        if kino and not prod and kino.product_id:
            prod = session.scalar(select(Product).where(Product.id == kino.product_id))
        if kino and not prod:
            kino_no_hyphen = (kino.search_model_no or "").replace("-", "")
            prod = session.scalar(
                select(Product).where(
                    (Product.jan_code == kino.jan_code)
                    | (Product.search_model_no == kino.search_model_no)
                    | (Product.search_model_no == kino_no_hyphen)
                )
            )
        if prod and not kino:
            kino = session.scalar(
                select(ProductKinohyo).where(
                    (ProductKinohyo.product_id == prod.id)
                    | (ProductKinohyo.jan_code == prod.jan_code)
                    | (ProductKinohyo.search_model_no == prod.search_model_no)
                )
            )

    return prod, kino


def get_app(database_url: str | None = None) -> FastAPI:
    db_url = resolve_database_url(database_url)
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)

    # Seed initial 6-category kinohyo specs and sync master links
    with SessionLocal() as s:
        seed_kinohyo_specs(s)

    app = FastAPI(
        title="Cymbal Retail VMD 機能表・POP自動生成スタジオ",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_db():
        with SessionLocal() as session:
            yield session

    @app.get("/api/health")
    def health(session: Session = Depends(get_db)):
        master_count = session.scalar(select(func.count()).select_from(Product)) or 0
        kinohyo_count = session.scalar(select(func.count()).select_from(ProductKinohyo)) or 0
        mail_count = session.scalar(select(func.count()).select_from(BannerMailLog)) or 0
        return {
            "status": "ok",
            "service": "cymbal-spec-banner",
            "database_type": "sqlite" if db_url.startswith("sqlite") else "postgresql/alloydb",
            "master_product_count": master_count,
            "kinohyo_product_count": kinohyo_count,
            "mail_log_count": mail_count,
            "registration_app_url": os.environ.get("PRODUCT_REG_URL", ""),
        }

    @app.get("/api/categories")
    def list_categories(session: Session = Depends(get_db)):
        counts_rows = session.execute(
            select(ProductKinohyo.category, func.count()).group_by(ProductKinohyo.category)
        ).all()
        counts_map = {cat: cnt for cat, cnt in counts_rows}
        categories = []
        for cat_id, cat_def in CATEGORY_DEFINITIONS.items():
            categories.append(
                {
                    **cat_def,
                    "count": counts_map.get(cat_id, 0),
                }
            )
        return {
            "categories": categories,
            "door_layouts": DOOR_LAYOUT_MAP,
        }

    @app.get("/api/products")
    def list_products(
        category: str | None = Query(default=None),
        q: str | None = Query(default=None),
        only_kinohyo: bool = Query(default=False),
        session: Session = Depends(get_db),
    ):
        kino_rows = session.scalars(select(ProductKinohyo).order_by(ProductKinohyo.id)).all()
        prod_rows = session.scalars(select(Product).order_by(Product.id)).all()

        prod_by_id = {p.id: p for p in prod_rows}
        prod_by_jan = {p.jan_code: p for p in prod_rows if p.jan_code}
        prod_by_model = {}
        for p in prod_rows:
            if p.search_model_no:
                prod_by_model[p.search_model_no] = p
                prod_by_model[p.search_model_no.replace("-", "")] = p

        seen_prod_ids: set[int] = set()
        results: list[dict[str, Any]] = []

        for k in kino_rows:
            p = (
                (prod_by_id.get(k.product_id) if k.product_id else None)
                or prod_by_jan.get(k.jan_code)
                or prod_by_model.get(k.search_model_no)
                or prod_by_model.get((k.search_model_no or "").replace("-", ""))
            )
            if p:
                seen_prod_ids.add(p.id)
            results.append(_serialize_joined_product(p, k))

        if not only_kinohyo:
            for p in prod_rows:
                if p.id in seen_prod_ids:
                    continue
                results.append(_serialize_joined_product(p, None))

        if category and category != "all":
            results = [r for r in results if r["category"] == category]

        if q and q.strip():
            kw = q.strip().lower()
            results = [
                r
                for r in results
                if kw in (r.get("jan_code") or "").lower()
                or kw in (r.get("search_model_no") or "").lower()
                or kw in (r.get("maker_name") or "").lower()
                or kw in (r.get("product_name") or "").lower()
                or kw in (r.get("features") or "").lower()
            ]

        return {"items": results, "total": len(results)}

    @app.get("/api/products/{identifier}")
    def get_product(identifier: str, session: Session = Depends(get_db)):
        prod, kino = _find_product_and_kinohyo(session, identifier)
        if not prod and not kino:
            raise HTTPException(status_code=404, detail=f"Product not found: {identifier}")
        return _serialize_joined_product(prod, kino)

    @app.put("/api/products/{identifier}/specs")
    async def update_product_specs(
        identifier: str,
        payload: UpdateSpecsPayload,
        session: Session = Depends(get_db),
    ):
        """Saves banner configuration to the tool-dedicated `mst_product_kinohyo` table
        and persists the rendered JPEG/PDF binary to GCS and BigQuery.
        Product Master (`mst_product`) is strictly READ-ONLY and is never modified here.
        """
        prod, kino = _find_product_and_kinohyo(session, identifier)
        if not prod and not kino:
            raise HTTPException(status_code=404, detail=f"Product not found: {identifier}")

        category = payload.category or (kino.category if kino else None) or "tv"
        base_specs = default_specs_for_category(category)
        existing_specs = (kino.specs if kino and isinstance(kino.specs, dict) else {}) or {}
        new_specs = {**base_specs, **existing_specs, **(payload.specs or {})}

        if kino is None and prod is not None:
            kino = ProductKinohyo(
                product_id=prod.id,
                jan_code=prod.jan_code or str(new_specs.get("jan_code") or prod.search_model_no),
                search_model_no=prod.search_model_no,
                category=category,
                template_variant=payload.template_variant or "auto",
                specs=new_specs,
                updated_by="studio_user",
            )
            session.add(kino)
        elif kino is not None:
            kino.category = category
            if payload.template_variant:
                kino.template_variant = payload.template_variant
            kino.specs = new_specs
            kino.updated_at = now_utc()

        # NOTE: `mst_product` (`prod`) is strictly READ-ONLY in this tool and is NEVER mutated.
        session.commit()
        if kino:
            session.refresh(kino)

        joined = _serialize_joined_product(prod, kino)

        # Persist binary banner (JPEG + PDF) to GCS and BigQuery
        model_no = str(new_specs.get("model_no") or joined.get("search_model_no") or category).replace("/", "_")
        jpg_fname = f"Cymbal_機能表_{model_no}.jpg"
        pdf_fname = f"Cymbal_機能表_{model_no}.pdf"

        img = await resolve_banner_image_async(
            image_data_url=payload.image_data_url,
            category=category,
            specs=new_specs,
            product_info=joined,
        )
        jpg_bytes = _encode_image_to_jpeg(img, quality=96)
        pdf_bytes = _encode_image_to_pdf(img, category=category, specs=new_specs)

        jpg_meta = persist_banner_artifact(jpg_fname, jpg_bytes, "image/jpeg")
        pdf_meta = persist_banner_artifact(pdf_fname, pdf_bytes, "application/pdf")
        bq_uri = persist_banner_to_bigquery(
            jan_code=joined.get("jan_code", ""),
            search_model_no=joined.get("search_model_no", ""),
            category=category,
            maker_name=joined.get("maker_name", ""),
            product_name=joined.get("product_name", ""),
            specs=new_specs,
            gcs_jpeg_uri=jpg_meta.get("gcs_uri") or jpg_meta.get("download_url", ""),
            gcs_pdf_uri=pdf_meta.get("gcs_uri") or pdf_meta.get("download_url", ""),
            jpg_bytes=jpg_bytes,
        )

        joined["saved_storage"] = {
            "gcs_jpeg_uri": jpg_meta.get("gcs_uri") or jpg_meta.get("download_url", ""),
            "gcs_pdf_uri": pdf_meta.get("gcs_uri") or pdf_meta.get("download_url", ""),
            "bigquery_uri": bq_uri,
            "master_readonly": True,
        }
        return joined

    @app.post("/api/products")
    def create_product(payload: CreateProductPayload, session: Session = Depends(get_db)):
        base_specs = default_specs_for_category(payload.category)
        merged_specs = {
            **base_specs,
            **(payload.specs or {}),
            "maker": payload.specs.get("maker") or payload.maker_name or base_specs.get("maker", ""),
            "model_no": payload.specs.get("model_no") or payload.search_model_no,
            "jan_code": payload.jan_code,
        }
        prod, kino = upsert_master_and_kinohyo(
            session,
            {
                "category": payload.category,
                "jan_code": payload.jan_code,
                "search_model_no": payload.search_model_no,
                "maker_name": payload.maker_name or merged_specs.get("maker", ""),
                "product_name": payload.product_name or payload.search_model_no,
                "class_code": payload.class_code,
                "edion_price": payload.edion_price,
                "long_warranty": payload.long_warranty,
                "features": payload.features,
                "specs": merged_specs,
            },
        )
        kino.specs = merged_specs
        session.commit()
        session.refresh(prod)
        session.refresh(kino)
        return _serialize_joined_product(prod, kino)

    @app.post("/api/products/{identifier}/ai-enrich")
    async def ai_enrich_product(
        identifier: str,
        category: str | None = Query(default=None),
        session: Session = Depends(get_db),
    ):
        prod, kino = _find_product_and_kinohyo(session, identifier)
        if not prod and not kino:
            raise HTTPException(status_code=404, detail=f"Product not found: {identifier}")

        joined = _serialize_joined_product(prod, kino)
        target_category = category or joined["category"]
        enriched = await enrich_specs_with_gemini(
            category=target_category,
            product_info=joined,
            current_specs=joined["specs"],
        )

        if kino is None and prod is not None:
            kino = ProductKinohyo(
                product_id=prod.id,
                jan_code=joined["jan_code"] or joined["search_model_no"],
                search_model_no=joined["search_model_no"],
                category=target_category,
                template_variant="auto",
                specs=enriched["specs"],
                ai_metadata={
                    "summary": enriched["summary"],
                    "sources": enriched["sources"],
                    "updated_keys": enriched["updated_keys"],
                    "model": enriched["model"],
                    "at": enriched["at"],
                },
                updated_by="gemini-2.5-flash",
            )
            session.add(kino)
        elif kino is not None:
            kino.category = target_category
            kino.specs = enriched["specs"]
            kino.ai_metadata = {
                "summary": enriched["summary"],
                "sources": enriched["sources"],
                "updated_keys": enriched["updated_keys"],
                "model": enriched["model"],
                "at": enriched["at"],
            }
            kino.updated_at = now_utc()

        session.commit()
        if kino:
            session.refresh(kino)
        return {
            "product": _serialize_joined_product(prod, kino),
            "ai_result": enriched,
        }

    @app.post("/api/import-excel")
    async def import_excel(
        file: UploadFile = File(...),
        session: Session = Depends(get_db),
    ):
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty Excel file")
        parsed = parse_kinohyo_excel(content, filename=file.filename or "")
        imported_items = []
        for item in parsed["items"]:
            prod, kino = upsert_master_and_kinohyo(session, item)
            kino.specs = item["specs"]
            session.flush()
            imported_items.append(_serialize_joined_product(prod, kino))
        session.commit()
        return {
            "filename": file.filename,
            "detected_category": parsed["category"],
            "imported_count": len(imported_items),
            "items": imported_items,
        }

    @app.post("/api/sync-master")
    def sync_master(session: Session = Depends(get_db)):
        """Re-links all `mst_product` rows with `mst_product_kinohyo` and creates kinohyo records for new master SKUs."""
        prod_rows = session.scalars(select(Product).order_by(Product.id)).all()
        linked_count = 0
        created_count = 0
        for p in prod_rows:
            kino = session.scalar(
                select(ProductKinohyo).where(
                    (ProductKinohyo.product_id == p.id)
                    | (ProductKinohyo.jan_code == p.jan_code)
                    | (ProductKinohyo.search_model_no == p.search_model_no)
                )
            )
            if kino:
                if kino.product_id != p.id:
                    kino.product_id = p.id
                    linked_count += 1
            else:
                inp = p.input_data if isinstance(p.input_data, dict) else {}
                inferred_cat = infer_category_from_product(
                    p.product_name, p.class_code, inp.get("features"), p.search_model_no
                )
                if inferred_cat:
                    specs = default_specs_for_category(inferred_cat)
                    specs["maker"] = p.maker_name or specs.get("maker", "")
                    specs["model_no"] = p.search_model_no
                    specs["jan_code"] = p.jan_code or ""
                    session.add(
                        ProductKinohyo(
                            product_id=p.id,
                            jan_code=p.jan_code or p.search_model_no,
                            search_model_no=p.search_model_no,
                            category=inferred_cat,
                            specs=specs,
                            ai_metadata={"source": "product-master sync"},
                            updated_by="sync_master",
                        )
                    )
                    created_count += 1
        session.commit()
        return {
            "status": "ok",
            "master_total": len(prod_rows),
            "linked_count": linked_count,
            "auto_created_kinohyo": created_count,
        }

    @app.post("/api/export/jpeg")
    async def export_jpeg(payload: ExportBannerPayload, session: Session = Depends(get_db)):
        prod, kino = (None, None)
        if payload.product_id or payload.jan_code:
            ident = str(payload.product_id or payload.jan_code)
            prod, kino = _find_product_and_kinohyo(session, ident)

        joined = _serialize_joined_product(prod, kino) if (prod or kino) else {}
        category = payload.category or joined.get("category") or "tv"
        specs = payload.specs or joined.get("specs") or default_specs_for_category(category)

        jpg_bytes = await generate_jpeg_bytes_async(
            image_data_url=payload.image_data_url,
            category=category,
            specs=specs,
            product_info=joined,
        )
        model_no = str(specs.get("model_no") or joined.get("search_model_no") or category).replace("/", "_")
        fname = payload.filename or f"Cymbal_機能表_{model_no}.jpg"
        persist_banner_artifact(fname, jpg_bytes, "image/jpeg")

        encoded_fname = urllib.parse.quote(fname)
        return Response(
            content=jpg_bytes,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_fname}",
            },
        )

    @app.post("/api/export/pdf")
    async def export_pdf(payload: ExportBannerPayload, session: Session = Depends(get_db)):
        prod, kino = (None, None)
        if payload.product_id or payload.jan_code:
            ident = str(payload.product_id or payload.jan_code)
            prod, kino = _find_product_and_kinohyo(session, ident)

        joined = _serialize_joined_product(prod, kino) if (prod or kino) else {}
        category = payload.category or joined.get("category") or "tv"
        specs = payload.specs or joined.get("specs") or default_specs_for_category(category)

        pdf_bytes = await generate_pdf_bytes_async(
            image_data_url=payload.image_data_url,
            category=category,
            specs=specs,
            product_info=joined,
        )
        model_no = str(specs.get("model_no") or joined.get("search_model_no") or category).replace("/", "_")
        fname = payload.filename or f"Cymbal_機能表_{model_no}.pdf"
        persist_banner_artifact(fname, pdf_bytes, "application/pdf")

        encoded_fname = urllib.parse.quote(fname)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_fname}",
            },
        )

    @app.post("/api/email/send")
    async def email_send(payload: SendEmailPayload, session: Session = Depends(get_db)):
        prod, kino = (None, None)
        if payload.product_id or payload.jan_code or payload.search_model_no:
            ident = str(payload.product_id or payload.jan_code or payload.search_model_no)
            prod, kino = _find_product_and_kinohyo(session, ident)

        joined = _serialize_joined_product(prod, kino) if (prod or kino) else {}
        category = payload.category or joined.get("category") or "tv"
        specs = dict(payload.specs or joined.get("specs") or default_specs_for_category(category))

        # Render once via Chromium async and encode both JPEG and PDF
        img = await resolve_banner_image_async(
            image_data_url=payload.image_data_url,
            category=category,
            specs=specs,
            product_info=joined,
        )
        specs["_pre_jpg_bytes"] = _encode_image_to_jpeg(img, quality=96)
        specs["_pre_pdf_bytes"] = _encode_image_to_pdf(img, category=category, specs=specs)

        res = send_banner_email(
            session,
            to_email=payload.to_email,
            cc_email=payload.cc_email,
            subject=payload.subject,
            body=payload.body,
            attachment_format=payload.attachment_format,
            product_id=joined.get("product_id"),
            jan_code=payload.jan_code or joined.get("jan_code"),
            search_model_no=payload.search_model_no or joined.get("search_model_no") or str(specs.get("model_no", "")),
            category=category,
            specs=specs,
            product_info=joined,
            image_data_url=payload.image_data_url,
        )
        return res

    @app.get("/api/email/logs")
    def email_logs(session: Session = Depends(get_db)):
        rows = session.scalars(select(BannerMailLog).order_by(BannerMailLog.id.desc()).limit(50)).all()
        return {
            "items": [
                {
                    "id": r.id,
                    "product_id": r.product_id,
                    "jan_code": r.jan_code,
                    "search_model_no": r.search_model_no,
                    "category": r.category,
                    "to_email": r.to_email,
                    "cc_email": r.cc_email,
                    "subject": r.subject,
                    "body": r.body,
                    "attachment_format": r.attachment_format,
                    "status": r.status,
                    "delivery_method": r.delivery_method,
                    "jpeg_uri": r.jpeg_uri,
                    "pdf_uri": r.pdf_uri,
                    "meta": r.meta,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                }
                for r in rows
            ]
        }

    @app.post("/api/email/logs/{log_id}/relayed")
    def mark_email_relayed(
        log_id: int,
        status: str = Query(default="RELAYED"),
        delivery_method: str = Query(default="gmail_cli_relay"),
        error_message: str | None = Query(default=None),
        session: Session = Depends(get_db),
    ):
        row = session.scalar(select(BannerMailLog).where(BannerMailLog.id == log_id))
        if not row:
            raise HTTPException(status_code=404, detail="Mail log not found")
        row.status = status
        row.delivery_method = delivery_method
        if status in ("RELAYED", "SENT"):
            row.sent_at = now_utc()
            row.error_message = None
        elif error_message:
            row.error_message = error_message[:300]
        session.commit()
        return {"id": row.id, "status": row.status, "delivery_method": row.delivery_method}

    @app.get("/api/files/banners/{filename}")
    def download_stored_banner(filename: str):
        local_dir = os.path.abspath(os.environ.get("LOCAL_STORAGE_DIR", "./data/banners"))
        fpath = os.path.join(local_dir, os.path.basename(filename))
        if not os.path.exists(fpath):
            raise HTTPException(status_code=404, detail="File not found")
        mtype = "application/pdf" if filename.lower().endswith(".pdf") else "image/jpeg"
        return FileResponse(fpath, media_type=mtype, filename=os.path.basename(filename))

    @app.get("/api/templates")
    def list_templates(
        category: str | None = Query(default=None),
        only_published: bool = Query(default=False),
        session: Session = Depends(get_db),
    ):
        """Returns the 6 built-in category presets plus any custom saved templates (`mst_banner_template`)."""
        presets = get_default_templates(category)
        stmt = select(BannerTemplate).order_by(BannerTemplate.updated_at.desc())
        if category and category != "all":
            stmt = stmt.where(BannerTemplate.category == category)
        saved_rows = session.scalars(stmt).all()

        saved_items: list[dict[str, Any]] = []
        for r in saved_rows:
            sc = dict(r.schema_json or {})
            status_val = sc.get("status", "draft")
            if only_published and status_val != "published":
                continue
            sc.update(
                {
                    "template_id": r.template_id,
                    "name": r.name,
                    "category": r.category,
                    "orientation": r.orientation,
                    "is_preset": bool(r.is_preset),
                    "status": status_val,
                    "is_category_default": bool(sc.get("is_category_default", False)),
                    "assigned_models": list(sc.get("assigned_models") or []),
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
            )
            saved_items.append(sc)

        return {
            "items": saved_items + presets,
            "total": len(saved_items) + len(presets),
        }

    @app.post("/api/templates")
    async def save_template(
        payload: SaveTemplatePayload,
        session: Session = Depends(get_db),
    ):
        """Saves a customized banner template & field mapping (as `draft` or `published`) to `mst_banner_template`
        and GCS/BigQuery. Also links assigned products (`mst_product_kinohyo.template_variant = tid`) if specified.
        Product Master (`mst_product`) is strictly READ-ONLY.
        """
        import uuid

        tid = (payload.template_id or "").strip()
        if not tid or tid.startswith("preset_") or tid.startswith("blank_"):
            tid = f"custom_{payload.category}_{uuid.uuid4().hex[:8]}"

        # If this template is marked as category default and published, unset previous category default
        if payload.status == "published" and payload.is_category_default:
            other_rows = session.scalars(
                select(BannerTemplate).where(BannerTemplate.category == payload.category)
            ).all()
            for orow in other_rows:
                if orow.template_id != tid and isinstance(orow.schema_json, dict):
                    osc = dict(orow.schema_json)
                    if osc.get("is_category_default"):
                        osc["is_category_default"] = False
                        orow.schema_json = osc

        schema_data = dict(payload.schema_json or {})
        schema_data["template_id"] = tid
        schema_data["name"] = payload.name
        schema_data["category"] = payload.category
        schema_data["orientation"] = payload.orientation
        schema_data["is_preset"] = False
        schema_data["status"] = payload.status
        schema_data["is_category_default"] = bool(payload.is_category_default)
        schema_data["assigned_models"] = list(payload.assigned_models or [])

        existing = session.scalar(select(BannerTemplate).where(BannerTemplate.template_id == tid))
        if existing:
            existing.name = payload.name
            existing.category = payload.category
            existing.orientation = payload.orientation
            existing.schema_json = schema_data
            existing.updated_at = now_utc()
            row = existing
        else:
            row = BannerTemplate(
                template_id=tid,
                name=payload.name,
                category=payload.category,
                orientation=payload.orientation,
                is_preset=0,
                schema_json=schema_data,
            )
            session.add(row)

        # Link assigned products in `mst_product_kinohyo` (`template_variant = tid`) when published
        if payload.status == "published":
            if payload.is_category_default:
                cat_kinos = session.scalars(
                    select(ProductKinohyo).where(ProductKinohyo.category == payload.category)
                ).all()
                for ck in cat_kinos:
                    if not ck.template_variant or ck.template_variant == "auto" or ck.template_variant == tid:
                        ck.template_variant = tid
            if payload.assigned_models:
                for m_ident in payload.assigned_models:
                    _, ck = _find_product_and_kinohyo(session, m_ident)
                    if ck:
                        ck.template_variant = tid

        session.commit()
        session.refresh(row)

        saved_storage: dict[str, Any] = {"master_readonly": True, "status": payload.status}
        if payload.image_data_url:
            img = await resolve_banner_image_async(
                image_data_url=payload.image_data_url,
                category=payload.category,
                specs={},
            )
            jpg_bytes = _encode_image_to_jpeg(img, quality=96)
            pdf_bytes = _encode_image_to_pdf(img, category=payload.category, specs={})
            jpg_meta = persist_banner_artifact(f"TEMPLATE_{tid}.jpg", jpg_bytes, "image/jpeg")
            pdf_meta = persist_banner_artifact(f"TEMPLATE_{tid}.pdf", pdf_bytes, "application/pdf")
            bq_uri = persist_banner_to_bigquery(
                jan_code=tid,
                search_model_no=payload.name,
                category=payload.category,
                maker_name=f"TEMPLATE_{payload.status.upper()}",
                product_name=payload.name,
                specs=schema_data,
                gcs_jpeg_uri=jpg_meta.get("gcs_uri") or jpg_meta.get("download_url", ""),
                gcs_pdf_uri=pdf_meta.get("gcs_uri") or pdf_meta.get("download_url", ""),
                jpg_bytes=jpg_bytes,
            )
            saved_storage.update(
                {
                    "gcs_jpeg_uri": jpg_meta.get("gcs_uri") or jpg_meta.get("download_url", ""),
                    "gcs_pdf_uri": pdf_meta.get("gcs_uri") or pdf_meta.get("download_url", ""),
                    "bigquery_uri": bq_uri,
                }
            )

        out = dict(row.schema_json or {})
        out["template_id"] = row.template_id
        out["name"] = row.name
        out["category"] = row.category
        out["orientation"] = row.orientation
        out["is_preset"] = False
        out["status"] = payload.status
        out["is_category_default"] = bool(payload.is_category_default)
        out["assigned_models"] = list(payload.assigned_models or [])
        out["saved_storage"] = saved_storage
        return out

    @app.delete("/api/templates/{template_id}")
    def delete_template(template_id: str, session: Session = Depends(get_db)):
        row = session.scalar(select(BannerTemplate).where(BannerTemplate.template_id == template_id))
        if not row:
            raise HTTPException(status_code=404, detail="Template not found")
        session.delete(row)
        session.commit()
        return {"deleted": template_id}

    @app.post("/api/templates/analyze-image")
    async def analyze_template_image(
        file: UploadFile = File(...),
        category: str = Query(default="tv"),
    ):
        """Analyzes an uploaded banner layout image (JPEG/PNG/WebP) with Vertex AI Gemini 2.5 Flash Vision
        and returns an automatically constructed `TemplateSchema` JSON + extracted spec values.
        """
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty image file")
        mime_type = file.content_type or "image/jpeg"
        result = await analyze_banner_image_with_gemini(
            image_bytes=content,
            mime_type=mime_type,
            category_hint=category,
            filename=file.filename or "layout.jpg",
        )
        return result

    static_dir = os.environ.get("STATIC_DIR") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../web/dist")
    )
    if os.path.isdir(static_dir):
        assets_dir = os.path.join(static_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str):
            candidate = os.path.join(static_dir, full_path)
            if full_path and os.path.isfile(candidate):
                return FileResponse(candidate)
            index_file = os.path.join(static_dir, "index.html")
            if os.path.isfile(index_file):
                return FileResponse(index_file)
            raise HTTPException(status_code=404, detail="Not Found")

    return app
