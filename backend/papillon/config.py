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
    dialer_enabled: bool = field(default_factory=lambda: _env("DIALER_ENABLED", "true") == "true")

    # Brand used in the call script and messages
    brand_name: str = field(default_factory=lambda: _env("BRAND_NAME", "Papillon Interiors"))
    brand_agent_name: str = field(default_factory=lambda: _env("BRAND_AGENT_NAME", "Meera"))
    brand_studio_address: str = field(default_factory=lambda: _env("BRAND_STUDIO_ADDRESS", "our Bengaluru studio"))

    # Exotel (Connect Voice AI API)
    exotel_api_key: str = field(default_factory=lambda: _env("EXOTEL_API_KEY"))
    exotel_api_token: str = field(default_factory=lambda: _env("EXOTEL_API_TOKEN"))
    exotel_account_sid: str = field(default_factory=lambda: _env("EXOTEL_ACCOUNT_SID"))
    exotel_caller_id: str = field(default_factory=lambda: _env("EXOTEL_CALLER_ID"))
    exotel_base_url: str = field(default_factory=lambda: _env("EXOTEL_BASE_URL", "https://api.in.exotel.com"))
    exotel_record: bool = field(default_factory=lambda: _env("EXOTEL_RECORD", "true") == "true")

    # Speech + LLM
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "gpt-4.1-mini"))
    stt_provider: str = field(default_factory=lambda: _env("STT_PROVIDER", "deepgram"))   # deepgram | sarvam
    tts_provider: str = field(default_factory=lambda: _env("TTS_PROVIDER", "sarvam"))     # sarvam | cartesia
    deepgram_api_key: str = field(default_factory=lambda: _env("DEEPGRAM_API_KEY"))
    sarvam_api_key: str = field(default_factory=lambda: _env("SARVAM_API_KEY"))
    sarvam_voice: str = field(default_factory=lambda: _env("SARVAM_VOICE", "priya"))
    sarvam_tts_model: str = field(default_factory=lambda: _env("SARVAM_TTS_MODEL", "bulbul:v3"))
    cartesia_api_key: str = field(default_factory=lambda: _env("CARTESIA_API_KEY"))
    cartesia_voice: str = field(default_factory=lambda: _env("CARTESIA_VOICE"))

    # WhatsApp Cloud API
    wa_token: str = field(default_factory=lambda: _env("WA_TOKEN"))
    wa_phone_number_id: str = field(default_factory=lambda: _env("WA_PHONE_NUMBER_ID"))
    wa_verify_token: str = field(default_factory=lambda: _env("WA_VERIFY_TOKEN"))
    wa_app_secret: str = field(default_factory=lambda: _env("WA_APP_SECRET"))
    wa_tpl_missed_call: str = field(default_factory=lambda: _env("WA_TPL_MISSED_CALL", "papillon_missed_call"))
    wa_tpl_intro: str = field(default_factory=lambda: _env("WA_TPL_INTRO", "papillon_enquiry_intro"))
    wa_tpl_forward: str = field(default_factory=lambda: _env("WA_TPL_FORWARD", "papillon_new_lead"))
    wa_tpl_lang: str = field(default_factory=lambda: _env("WA_TPL_LANG", "en"))

    # Meta Lead Ads
    meta_verify_token: str = field(default_factory=lambda: _env("META_VERIFY_TOKEN"))
    meta_page_token: str = field(default_factory=lambda: _env("META_PAGE_TOKEN"))
    meta_app_secret: str = field(default_factory=lambda: _env("META_APP_SECRET"))
    graph_version: str = field(default_factory=lambda: _env("META_GRAPH_VERSION", "v21.0"))

    # Google Ads lead form webhook
    google_lead_key: str = field(default_factory=lambda: _env("GOOGLE_LEAD_KEY"))

    # Email (any SMTP — Zoho, Google Workspace, Brevo…)
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    mail_from: str = field(default_factory=lambda: _env("MAIL_FROM"))
    dashboard_url: str = field(default_factory=lambda: _env("DASHBOARD_URL", "https://papillon-leads.vercel.app").rstrip("/"))


cfg = Config()
