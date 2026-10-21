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
    def _fetch_status_sync(self) -> Dict[str, Any]:
        for base_url in config.get_backend_urls():
            try:
                req = urllib.request.Request(f"{base_url}/api/status", headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                logger.debug(f"Failed to fetch status from {base_url}: {e}")
        return {}

    async def fetch_status(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self._fetch_status_sync)

    async def get_major_events(self, limit: int = 30) -> List[Dict[str, Any]]:
        status = await self.fetch_status()
        audit_events = status.get("audit", [])
        tasks = status.get("backups", {}).get("tasks", [])
        services = status.get("services", [])

        combined_events = []

        # 1. Add audit events (container actions, route setups, auto-gen)
        for a in audit_events:
            combined_events.append({
                "source": "audit",
                "time": a.get("time", datetime.datetime.now(datetime.timezone.utc).isoformat()),
                "action": a.get("action", ""),
                "target": a.get("target", ""),
                "actor": a.get("actor", ""),
                "success": a.get("success", True),
                "message": a.get("message", ""),
            })

        # 2. Add major Proxmox cluster tasks (vzdump, start, stop, push_file)
        for t in tasks[:30]:
            ttype = t.get("type", "").lower()
            if any(k in ttype for k in ["vzdump", "start", "stop", "create", "restart"]):
                start_val = t.get("start")
                if isinstance(start_val, (int, float)):
                    t_str = datetime.datetime.fromtimestamp(start_val, datetime.timezone.utc).isoformat()
                else:
                    t_str = str(start_val) if start_val else datetime.datetime.now(datetime.timezone.utc).isoformat()

                combined_events.append({
                    "source": "proxmox_task",
                    "time": t_str,
                    "action": t.get("type", ""),
                    "target": t.get("target", "pve"),
                    "status": t.get("status", "OK"),
                    "description": t.get("description", t.get("type", "")),
                })

        # Sort combined events by time descending
        def get_time(item):
            try:
                return datetime.datetime.fromisoformat(item.get("time", "")).timestamp()
            except Exception:
                return 0

        combined_events.sort(key=get_time, reverse=True)

        if not combined_events:
            return [
                {
                    "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "type": "system",
                    "severity": "info",
                    "title": "RS Hub Monitoring Active",
                    "summary": "AI Agent actively tracking container events, Cloudflare routes, and host tasks.",
                }
            ]

        # Use Gemini 3.5 Flash Lite to produce plain-English 1-sentence summaries
        prompt = f"""You are a Homelab Monitoring Assistant.
Analyze these recent homelab infrastructure events (container setups, Cloudflare routing, Proxmox tasks, user actions):
{json.dumps(combined_events[:20])}

For each event, produce a clean human-friendly summary in this JSON array format:
[
  {{
    "time": "ISO-8601 timestamp string matching the original event time",
    "type": "container" | "route" | "backup" | "lxc" | "system",
    "severity": "info" | "warning" | "critical",
    "title": "Short title (e.g. 'Traefik Whoami Deployed & Routed', 'Debian LXC 101 Backup')",
    "summary": "1 concise sentence explaining what happened in plain English."
  }}
]

Focus on what happened clearly. Output strictly valid JSON."""

        try:
            ai_res = await gemini.generate_json(
                prompt=prompt,
                system_instruction="You are a precise JSON generator summarizing homelab events.",
            )
            data = ai_res.get("data", [])
            if isinstance(data, list) and len(data) > 0:
                return data[:limit]
        except Exception as e:
            logger.warning(f"Gemini event summarization fallback: {e}")

        # Deterministic fallback if Gemini is unreachable
        fallback_results = []
        for ev in combined_events[:limit]:
            source = ev.get("source")
            msg = ev.get("message") or ev.get("description") or ev.get("action", "")
            target = ev.get("target", "")
            is_ok = ev.get("success", True) if "success" in ev else ev.get("status") == "OK"

            if "whoami" in target.lower() or "whoami" in msg.lower():
                title = "Traefik Whoami Deployed & Routed"
                summary = "Autonomous Setup: Generated pve.toml and Cloudflare route whoami.958901.xyz."
                ev_type = "container"
            elif "create_docker" in str(ev.get("action")):
                title = f"Container Stack {target} Created"
                summary = f"Stack {target} was configured and deployed successfully."
                ev_type = "container"
            elif "create_route" in str(ev.get("action")):
                title = f"Cloudflare Route Published"
                summary = f"Published route for {target} to Cloudflare edge tunnel."
                ev_type = "route"
            elif "vzdump" in str(ev.get("action")).lower():
                title = f"Proxmox Backup Completed"
                summary = f"Automated vzdump backup of target {target} finished successfully."
                ev_type = "backup"
            else:
                title = f"Event: {ev.get('action', 'Task')}"
                summary = str(msg)[:150]
                ev_type = "system"

            fallback_results.append({
                "time": ev.get("time", datetime.datetime.now(datetime.timezone.utc).isoformat()),
                "type": ev_type,
                "severity": "info" if is_ok else "warning",
                "title": title,
                "summary": summary,
            })

        return fallback_results

events_service = EventsService()
