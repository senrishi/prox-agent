import os
import pathlib
from typing import List

def load_env_file():
    candidates = [pathlib.Path(".env"), pathlib.Path(__file__).parent.parent / ".env"]
    for env_path in candidates:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break

load_env_file()

class Config:
    @staticmethod
    def get_api_keys() -> List[str]:
        raw = os.getenv("GEMINI_API_KEYS", "")
        keys = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
        return keys

    PRIMARY_MODEL: str = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.5-flash-lite")
    
    @staticmethod
    def get_fallback_models() -> List[str]:
        raw = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite,gemini-3.5-flash,gemini-2.5-flash")
        return [m.strip() for m in raw.split(",") if m.strip()]

    HOMELAB_API_URL: str = os.getenv("HOMELAB_API_URL", "http://homelab-backend:8080")
    HOMELAB_PUBLIC_URL: str = os.getenv("HOMELAB_PUBLIC_URL", "https://home.958901.xyz")
    PROXMOX_HOST: str = os.getenv("PROXMOX_HOST", "192.168.1.50")
    DOMAIN: str = os.getenv("DOMAIN", "958901.xyz")
    PORT: int = int(os.getenv("PORT", "8090"))

    @classmethod
    def get_backend_urls(cls) -> List[str]:
        urls = []
        if cls.HOMELAB_API_URL:
            urls.append(cls.HOMELAB_API_URL)
        if cls.HOMELAB_PUBLIC_URL and cls.HOMELAB_PUBLIC_URL != cls.HOMELAB_API_URL:
            urls.append(cls.HOMELAB_PUBLIC_URL)
        return urls

config = Config()
