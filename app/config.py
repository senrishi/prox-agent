import os
class Config:
    HOMELAB_API_URL = os.getenv("HOMELAB_API_URL", "http://homelab-backend:8080").rstrip("/")
    SERVICE_TOKEN = os.getenv("RS_SERVICE_TOKEN", "")
    DOMAIN = os.getenv("DOMAIN", os.getenv("HOMELAB_DOMAIN", "958901.xyz"))
    PRIMARY_MODEL = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.5-flash-lite")
    PORT = 8090
    @staticmethod
    def get_api_keys():
        return [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").replace("\n", ",").split(",") if k.strip()]
    @staticmethod
    def get_fallback_models():
        return [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite,gemini-3.5-flash").split(",") if m.strip()]
config = Config()
