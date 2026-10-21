import asyncio
import datetime
import json
import logging
import urllib.request
from typing import Any, Dict, List

from app.config import config
from app.gemini_client import gemini

logger = logging.getLogger("prox-agent.rankings")

class RankingsService:
    def __init__(self):
        # In-memory history cache to compute rank movements
        self._history: Dict[str, int] = {}

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

    async def get_performance_rankings(self) -> Dict[str, Any]:
        status = await self.fetch_status()
        lxcs = status.get("lxcs", [])
        routes = status.get("routes", [])

        # Gather all containers across all LXCs
        all_containers = []
        for l in lxcs:
            lxc_id = l.get("id")
            for c in l.get("containers", []):
                mem_bytes = c.get("memory_bytes", 0)
                mem_pct = c.get("memory_percent", 0.0)
                cpu_pct = c.get("cpu", 0.0)
                name = c.get("name")
                if name:
                    all_containers.append({
                        "name": name,
                        "lxc_id": lxc_id,
                        "memory_bytes": mem_bytes,
                        "memory_text": c.get("memory_text", f"{round(mem_bytes/1024**2, 1)} MB"),
                        "memory_percent": mem_pct,
                        "cpu_percent": cpu_pct,
                        "state": c.get("state", "unknown"),
                    })

        # 1. Top Memory Consumers
        memory_ranking = sorted(all_containers, key=lambda x: (x["memory_percent"], x["memory_bytes"]), reverse=True)
        top_memory = []
        for rank, c in enumerate(memory_ranking[:10], 1):
            key = f"mem_{c['name']}"
            prev_rank = self._history.get(key, rank)
            self._history[key] = rank
            delta = prev_rank - rank  # Positive means moved up
            
            top_memory.append({
                "rank": rank,
                "name": c["name"],
                "lxc_id": c["lxc_id"],
                "memory_text": c["memory_text"],
                "memory_percent": c["memory_percent"],
                "state": c["state"],
                "movement": "up" if delta > 0 else ("down" if delta < 0 else "same"),
                "delta": abs(delta),
            })

        # 2. Top CPU Consumers
        cpu_ranking = sorted(all_containers, key=lambda x: x["cpu_percent"], reverse=True)
        top_cpu = []
        for rank, c in enumerate(cpu_ranking[:10], 1):
            top_cpu.append({
                "rank": rank,
                "name": c["name"],
                "lxc_id": c["lxc_id"],
                "cpu_percent": c["cpu_percent"],
                "state": c["state"],
            })

        # 3. Route Traffic Rankings
        route_rankings = []
        for rank, r in enumerate(routes, 1):
            route_rankings.append({
                "rank": rank,
                "name": r.get("name"),
                "url": r.get("url"),
                "target": f"{r.get('scheme', 'http')}://{r.get('host')}:{r.get('port')}",
                "scheme": r.get("scheme", "http"),
            })

        # 4. Generate AI Executive Insight
        insight = "All containers and routes operating at standard resource efficiency."
        try:
            top_summary = [f"{c['name']} ({c['memory_text']}, {c['cpu_percent']}% CPU)" for c in top_memory[:4]]
            prompt = f"""Summarize in 2 sentences the top resource consumers in this homelab today:
Top containers: {', '.join(top_summary)}
Routes monitored: {len(routes)}."""
            ai_res = await gemini.generate_content(prompt=prompt, temperature=0.3)
            insight = ai_res.get("text", insight).strip()
        except Exception:
            pass

        return {
            "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "top_memory": top_memory,
            "top_cpu": top_cpu,
            "top_routes": route_rankings,
            "ai_insight": insight,
        }

rankings_service = RankingsService()
