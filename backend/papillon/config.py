"""All runtime configuration comes from environment variables (see .env.example)."""

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _list(name: str) -> list[str]:
    return [x.strip() for x in _env(name).split(",") if x.strip()]


@dataclass(frozen=True)
class Config:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    public_base_url: str = field(default_factory=lambda: _env("PUBLIC_BASE_URL", "https://leads.example.com").rstrip("/"))
    admin_token: str = field(default_factory=lambda: _env("ADMIN_TOKEN"))
    signing_secret: str = field(default_factory=lambda: _env("SIGNING_SECRET", "change-me"))
    allowed_origins: list[str] = field(default_factory=lambda: _list("ALLOWED_ORIGINS"))
    dialer_enabled: bool = field(default_factory=lambda: _env("FOLLOWUP_ENABLED", _env("DIALER_ENABLED", "true")) == "true")

    # Brand used in the call script and messages
    brand_name: str = field(default_factory=lambda: _env("BRAND_NAME", "Papillon Interiors"))
    brand_agent_name: str = field(default_factory=lambda: _env("BRAND_AGENT_NAME", "Meera"))
    brand_studio_address: str = field(default_factory=lambda: _env("BRAND_STUDIO_ADDRESS", "our Bengaluru studio"))

    # Language model for the WhatsApp assistant — any OpenAI-compatible API. Default: Groq (free tier)
    llm_api_url: str = field(default_factory=lambda: _env("LLM_API_URL", "https://api.groq.com/openai/v1/chat/completions"))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "llama-3.3-70b-versatile"))

    # WhatsApp Cloud API
    wa_token: str = field(default_factory=lambda: _env("WA_TOKEN"))
    wa_phone_number_id: str = field(default_factory=lambda: _env("WA_PHONE_NUMBER_ID"))
    wa_verify_token: str = field(default_factory=lambda: _env("WA_VERIFY_TOKEN"))
    wa_app_secret: str = field(default_factory=lambda: _env("WA_APP_SECRET"))
    wa_tpl_reminder: str = field(default_factory=lambda: _env("WA_TPL_REMINDER", "papillon_enquiry_reminder"))
    wa_tpl_intro: str = field(default_factory=lambda: _env("WA_TPL_INTRO", "papillon_enquiry_intro"))
    wa_tpl_forward: str = field(default_factory=lambda: _env("WA_TPL_FORWARD", "papillon_new_lead"))
    wa_tpl_lang: str = field(default_factory=lambda: _env("WA_TPL_LANG", "en"))

    # Meta Lead Ads
    meta_verify_token: str = field(default_factory=lambda: _env("META_VERIFY_TOKEN"))
    meta_page_token: str = field(default_factory=lambda: _env("META_PAGE_TOKEN"))
    meta_app_secret: str = field(default_factory=lambda: _env("META_APP_SECRET"))
    graph_version: str = field(default_factory=lambda: _env("META_GRAPH_VERSION", "v21.0"))

    # Crawler (Prospects page). GOOGLE_MAPS_KEY is optional — OpenStreetMap is used either way
    crawler_enabled: bool = field(default_factory=lambda: _env("CRAWLER_ENABLED", "true") == "true")
    google_maps_key: str = field(default_factory=lambda: _env("GOOGLE_MAPS_KEY"))

    # Google Ads lead form webhook
    google_lead_key: str = field(default_factory=lambda: _env("GOOGLE_LEAD_KEY"))

    # Email (any SMTP — Zoho, Google Workspace, Brevo…)
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    mail_from: str = field(default_factory=lambda: _env("MAIL_FROM"))
    dashboard_url: str = field(default_factory=lambda: _env("DASHBOARD_URL", "https://leads.papilloninteriors.in").rstrip("/"))


cfg = Config()
