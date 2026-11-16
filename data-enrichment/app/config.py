"""Application settings (env-overridable)."""
import os

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """NOTE: env names that collide with the shared repo install/config.env (BQ_DATASET=cymbal, GEMINI_MODEL=…)
    use ENRICH_* aliases first so sourcing install/config.env never points enrichment tables at `cymbal`."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_id: str = Field("", validation_alias=AliasChoices("PROJECT_ID", "GOOGLE_CLOUD_PROJECT"))
    bq_dataset: str = Field("cymbal_enrichment", validation_alias=AliasChoices("ENRICH_BQ_DATASET"))
    bq_source_dataset: str = Field("cymbal", validation_alias=AliasChoices("BQ_SOURCE_DATASET", "BQ_DATASET"))
    bq_source_table_name: str = "products"
    bq_source_table: str = ""
    bq_location: str = Field("asia-northeast1", validation_alias=AliasChoices("BQ_LOCATION", "REGION"))

    # Online (live) enrichment default. Selectable Gemini 3.x+ models are listed/probed in app/models.py.
    gemini_model: str = Field("gemini-3.8-flash", validation_alias=AliasChoices("ENRICH_GEMINI_MODEL", "GEMINI_MODEL"))
    gemini_fallback_model: str = "gemini-3.5-flash"
    vertex_location: str = Field("global", validation_alias=AliasChoices("VERTEX_LOCATION", "GEMINI_LOCATION"))
    thinking_level: str = "LOW"

    # Batch prediction
    batch_model: str = Field("gemini-3.8-flash", validation_alias=AliasChoices("ENRICH_BATCH_MODEL", "ENRICH_GEMINI_MODEL", "GEMINI_MODEL"))
    batch_location: str = "global"
    batch_gcs_prefix: str = "_batch"

    # Governance
    auto_approve_threshold: float = 0.90

    # Cost display: official LIST prices per model live in app/pricing.py
    usd_jpy: float = 150.0

    # Use in-memory demo data (no GCP) – for tests / offline dev
    offline: bool = False

    # ── Seasonal image generation (Gemini image models on Vertex AI, global) ──
    image_model: str = Field("gemini-3.1-flash-image", validation_alias=AliasChoices("IMAGE_MODEL"))
    image_model_pro: str = "gemini-3-pro-image"
    image_model_fallback: str = "gemini-2.5-flash-image"
    image_bucket: str = Field("", validation_alias=AliasChoices("ENRICH_IMAGE_BUCKET", "IMAGE_BUCKET"))
    docs_prefix: str = "_docs_uploads"
    image_default_size: int = 600
    image_fidelity_threshold: float = 0.7
    public_base_url: str = ""
    update_aics: bool = True

    # Cross links: online storefront (ADK) and optional external studio URLs
    store_url: str = Field("", validation_alias=AliasChoices("STORE_URL", "ONLINE_STORE_URL"))
    flyer_url: str = ""
    brand_name: str = Field("Cymbal Retail", validation_alias=AliasChoices("BRAND_NAME"))

    @model_validator(mode="after")
    def _derive_defaults(self) -> "Settings":
        if not self.project_id:
            self.project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or "your-gcp-project-id"
        if not self.bq_source_table:
            self.bq_source_table = f"{self.project_id}.{self.bq_source_dataset}.{self.bq_source_table_name}"
        if self.bq_dataset == self.bq_source_dataset:
            raise ValueError(f"enrichment dataset must differ from the source dataset ({self.bq_dataset})")
        if not self.image_bucket:
            self.image_bucket = f"products_images_{self.project_id}"
        return self

    @property
    def dataset_ref(self) -> str:
        return f"{self.project_id}.{self.bq_dataset}"


settings = Settings()
