import asyncio
import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.config import config

logger = logging.getLogger("prox-agent.gemini")
logging.basicConfig(level=logging.INFO)

class GeminiClient:
    def __init__(self):
        self._key_index = 0
        self._lock = threading.Lock()

    def _get_next_key(self, keys: List[str]) -> str:
        with self._lock:
            key = keys[self._key_index % len(keys)]
            self._key_index = (self._key_index + 1) % len(keys)
            return key

    def _send_request_sync(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25.0) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)

    async def generate_content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        json_output: bool = False,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        keys = config.get_api_keys()
        if not keys:
            raise ValueError("No GEMINI_API_KEYS configured in environment")

        models = [config.PRIMARY_MODEL] + config.get_fallback_models()
        # Deduplicate while preserving order
        unique_models = []
        for m in models:
            if m not in unique_models:
                unique_models.append(m)

        last_error = None

        # Try models in priority order
        for model in unique_models:
            # For each model, try all available keys round-robin
            for attempt in range(len(keys)):
                key = self._get_next_key(keys)
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

                payload: Dict[str, Any] = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                    },
                }

                if system_instruction:
                    payload["systemInstruction"] = {
                        "parts": [{"text": system_instruction}]
                    }

                if json_output:
                    payload["generationConfig"]["responseMimeType"] = "application/json"

                try:
                    data = await asyncio.to_thread(self._send_request_sync, url, payload)
                    candidates = data.get("candidates", [])
                    if candidates and candidates[0].get("content", {}).get("parts"):
                        text = candidates[0]["content"]["parts"][0].get("text", "")
                        return {
                            "success": True,
                            "text": text,
                            "model": model,
                            "key_fingerprint": key[:6] + "..." + key[-4:],
                        }
                    last_error = f"Empty candidate parts in response from {model}"
                except urllib.error.HTTPError as e:
                    err_body = e.read().decode("utf-8", errors="ignore")[:200]
                    logger.warning(
                        f"Model {model} with key {key[:6]}... returned HTTP {e.code}: {err_body}"
                    )
                    last_error = f"HTTP {e.code}: {err_body}"
                except Exception as e:
                    logger.warning(f"Connection error to {model} with key {key[:6]}...: {e}")
                    last_error = str(e)

        raise RuntimeError(f"All Gemini API keys and models exhausted. Last error: {last_error}")

    async def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        res = await self.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
            json_output=True,
            temperature=temperature,
        )
        text = res["text"].strip()
        # Clean potential markdown fences
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        parsed = json.loads(text)
        return {
            "data": parsed,
            "model": res["model"],
            "key": res["key_fingerprint"],
        }

gemini = GeminiClient()
