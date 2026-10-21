import asyncio
import datetime
import json
import logging
import urllib.request
from typing import Any, Dict, List

from app.config import config
from app.gemini_client import gemini

logger = logging.getLogger("prox-agent.diagnostics")

class DiagnosticsService:
    def _fetch_status_sync(self, auth_token: str = "") -> Dict[str, Any]:
        token = auth_token or config.get_backend_token()
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = token if token.startswith("Bearer ") else f"Bearer {token}"

        for base_url in config.get_backend_urls():
            try:
                req = urllib.request.Request(f"{base_url}/api/status", headers=headers)
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                logger.debug(f"Failed to fetch status from {base_url}: {e}")
        return {}

    async def fetch_status(self, auth_token: str = "") -> Dict[str, Any]:
        return await asyncio.to_thread(self._fetch_status_sync, auth_token)

    async def run_diagnostics(self, auth_token: str = "") -> List[Dict[str, Any]]:
        status = await self.fetch_status(auth_token)
        if not status:
            return []

        anomalies = []
        host = status.get("host", {})
        lxcs = status.get("lxcs", [])

        # 1. Check Host CPU Temperatures
        sensors = host.get("sensors", {})
        pkg_temp = sensors.get("cpu_package")
        if pkg_temp and pkg_temp >= 78.0:
            anomalies.append({
                "component": "Host CPU Thermal",
                "severity": "warning" if pkg_temp < 85 else "critical",
                "symptom": f"CPU package temperature is elevated at {pkg_temp}°C (Critical threshold: 100°C).",
                "target": "pve",
            })

        # 2. Check Thin Pool and Storage Usage
        for store in host.get("storages", []):
            if store.get("total", 0) > 0:
                pct = round(store["used"] / store["total"] * 100, 1)
                if pct >= 80.0:
                    anomalies.append({
                        "component": f"Storage Pool '{store.get('name')}'",
                        "severity": "critical" if pct >= 90 else "warning",
                        "symptom": f"Storage pool '{store.get('name')}' is at {pct}% utilization ({round(store['used']/1024**3, 1)} GiB of {round(store['total']/1024**3, 1)} GiB).",
                        "target": store.get("name"),
                    })

        # 3. Check LXC Memory & Swap Caps
        for l in lxcs:
            lxc_id = l.get("id")
            mem_pct = round(l.get("memory", 0) / max(1, l.get("memory_limit", 1)) * 100, 1)
            if mem_pct >= 88.0:
                anomalies.append({
                    "component": f"LXC {lxc_id} ({l.get('name')})",
                    "severity": "warning" if mem_pct < 95 else "critical",
                    "symptom": f"LXC {lxc_id} RAM usage is at {mem_pct}% of configured limit ({round(l.get('memory', 0)/1024**2)} MB / {round(l.get('memory_limit', 0)/1024**2)} MB).",
                    "target": f"LXC {lxc_id}",
                })

            # Check individual container statuses
            for c in l.get("containers", []):
                state = c.get("state", "").lower()
                c_name = c.get("name")
                if state in ["exited", "restarting", "dead"]:
                    anomalies.append({
                        "component": f"Container {c_name}",
                        "severity": "critical",
                        "symptom": f"Container {c_name} in LXC {lxc_id} is in '{state}' state. Detail: {c.get('detail', 'No detail')}.",
                        "target": c_name,
                    })

        if not anomalies:
            return [
                {
                    "id": "diag-clean",
                    "severity": "healthy",
                    "component": "System Health",
                    "summary": "All containers, LXCs, and host storage pools are operating well within healthy thresholds.",
                    "suggested_fix": "No action needed.",
                    "target": "pve",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            ]

        # Use Gemini to generate diagnosis and actionable remediation
        prompt = f"""You are an elite Linux & Homelab System Administrator.
Analyze these detected system anomalies on a Proxmox VE host running Debian, Alpine, and Gentoo LXCs:
{json.dumps(anomalies, indent=2)}

For each anomaly, generate a structured diagnostic entry in JSON:
[
  {{
    "id": "diag-1",
    "severity": "critical" | "warning",
    "component": "e.g. Container bewcloud-website-1 or Storage local-lvm",
    "summary": "Clear, plain-English summary of what is happening and why.",
    "suggested_fix": "Exact, precise shell command or action to resolve this issue (e.g. 'pct set 101 -memory 2048' or 'docker compose restart <name>').",
    "target": "affected target name",
    "timestamp": "ISO-8601 timestamp"
  }}
]"""

        try:
            ai_res = await gemini.generate_json(
                prompt=prompt,
                system_instruction="You provide precise, actionable Linux homelab diagnostic recommendations in JSON format.",
            )
            data = ai_res.get("data", [])
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.warning(f"Gemini diagnostics fallback: {e}")

        # Fallback
        results = []
        for idx, a in enumerate(anomalies):
            results.append({
                "id": f"diag-{idx}",
                "severity": a.get("severity", "warning"),
                "component": a.get("component"),
                "summary": a.get("symptom"),
                "suggested_fix": "Check container logs via 'docker logs <container>' or allocate additional resources via Proxmox.",
                "target": a.get("target"),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
        return results

diagnostics_service = DiagnosticsService()
