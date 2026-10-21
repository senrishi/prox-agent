import asyncio
import datetime
import json
import logging
import urllib.request
from typing import Any, Dict, List

from app.config import config
from app.gemini_client import gemini

logger = logging.getLogger("prox-agent.events")

class EventsService:
    def _fetch_tasks_sync(self) -> List[Dict[str, Any]]:
        try:
            req = urllib.request.Request(f"{config.HOMELAB_API_URL}/api/status", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                status = json.loads(resp.read().decode("utf-8"))
                backups = status.get("backups", {})
                tasks = backups.get("tasks", [])
                return tasks
        except Exception as e:
            logger.warning(f"Failed to fetch tasks from backend: {e}")
        return []

    async def fetch_raw_tasks(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_tasks_sync)

    async def get_major_events(self, limit: int = 30) -> List[Dict[str, Any]]:
        raw_tasks = await self.fetch_raw_tasks()
        if not raw_tasks:
            return [
                {
                    "id": "evt-1",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "type": "system",
                    "severity": "info",
                    "title": "RS Hub Telemetry Active",
                    "summary": "Agent monitoring 3 LXCs, Cloudflare edge tunnel, and Tailscale tailnet.",
                    "target": "pve",
                }
            ]

        # Select only major/critical task types
        filtered_tasks = []
        for t in raw_tasks[:40]:
            ttype = t.get("type", "").lower()
            if any(k in ttype for k in ["vzdump", "start", "stop", "create", "restart", "config", "push_file"]):
                filtered_tasks.append(t)

        if not filtered_tasks:
            filtered_tasks = raw_tasks[:15]

        # Ask Gemini to summarize and classify them
        prompt = f"""You are a Homelab Monitoring Assistant.
Here is a list of recent Proxmox and container system tasks:
{json.dumps(filtered_tasks[:15])}

For each major event, produce a clean, human-friendly summary in this JSON array format:
[
  {{
    "id": "task-id-or-hash",
    "timestamp": "ISO-8601 timestamp or relative",
    "type": "backup" | "container" | "lxc" | "network" | "system",
    "severity": "info" | "success" | "warning" | "error",
    "title": "Short title (e.g. 'Debian LXC 101 vzdump Backup')",
    "summary": "1 concise sentence explaining what happened (e.g. 'Completed Google Drive snapshot backup successfully in 45s.')",
    "target": "LXC 101 or container name"
  }}
]

Exclude minor internal polling ticks. Focus on important events."""

        try:
            ai_res = await gemini.generate_json(
                prompt=prompt,
                system_instruction="You are an expert system observer producing clean JSON event logs.",
            )
            data = ai_res.get("data", [])
            if isinstance(data, list):
                return data[:limit]
        except Exception as e:
            logger.warning(f"Gemini event summarization fallback: {e}")

        # Fallback to direct mapping without AI if rate-limited
        results = []
        for idx, t in enumerate(filtered_tasks[:limit]):
            results.append({
                "id": f"task-{idx}",
                "timestamp": str(t.get("start", datetime.datetime.now().isoformat())),
                "type": t.get("type", "task"),
                "severity": "success" if t.get("status") == "OK" else "warning",
                "title": t.get("description", t.get("type", "Task")),
                "summary": f"Task {t.get('description')} finished with status {t.get('status')} on target {t.get('target')}.",
                "target": str(t.get("target", "pve")),
            })
        return results

events_service = EventsService()
