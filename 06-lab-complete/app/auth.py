"""
API Key authentication (tiêu chí 6).
"""
import hmac

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency kiểm tra header X-API-Key khớp AGENT_API_KEY; thiếu/sai → 401."""
    if not settings.agent_api_key or not api_key:
        raise HTTPException(status_code=401, detail="Missing or unconfigured API key")
    if not hmac.compare_digest(api_key, settings.agent_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
