import asyncio
import datetime as dt
import time
import httpx
from app.config import config

class TelemetryError(Exception): pass

class Telemetry:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.cached = None
        self.fetched = 0
    async def get(self):
        async with self.lock:
            if self.cached is not None and time.monotonic()-self.fetched < 15:
                return self.cached
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    res = await client.get(config.HOMELAB_API_URL + "/api/internal/status", headers={"X-Service-Token": config.SERVICE_TOKEN})
                res.raise_for_status()
                data = res.json()
                collected = dt.datetime.fromisoformat(data["updated"].replace("Z", "+00:00"))
                if dt.datetime.now(dt.timezone.utc)-collected > dt.timedelta(minutes=2) or data.get("telemetry_error"):
                    raise TelemetryError("Telemetry is stale")
                if not isinstance(data.get("lxcs"), list) or not data.get("host"):
                    raise TelemetryError("Telemetry inventory is incomplete")
            except TelemetryError:
                raise
            except Exception:
                raise TelemetryError("Homelab telemetry unavailable; check service authentication and collection") from None
            self.cached, self.fetched = data, time.monotonic()
            return data
telemetry = Telemetry()

class AnalysisCache:
    def __init__(self):
        self.items = {}
        self.lock = asyncio.Lock()
    async def get(self, key, generate, ttl=300):
        async with self.lock:
            current = self.items.get(key)
            if current and time.monotonic()-current[0] < ttl:
                return current[1]
            value = await generate()
            if len(self.items)>128:
                self.items.clear()
            self.items[key] = (time.monotonic(), value)
            return value
cache = AnalysisCache()
