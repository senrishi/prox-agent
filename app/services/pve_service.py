import asyncio
import json
import re
import urllib.request
from typing import Any, Dict, List, Optional

from app.config import config
from app.gemini_client import gemini

class PveService:
    def _fetch_subdomains_sync(self) -> List[str]:
        try:
            req = urllib.request.Request(f"{config.HOMELAB_API_URL}/api/status", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                routes = data.get("routes", [])
                return [r.get("name", "").lower() for r in routes if r.get("name")]
        except Exception:
            return ["home", "prox", "router", "pve", "pihole"]

    async def get_existing_subdomains(self) -> List[str]:
        return await asyncio.to_thread(self._fetch_subdomains_sync)

    async def analyze_and_generate(
        self,
        compose_yaml: str,
        stack_name: str,
        lxc_id: int = 100,
        host_ip: str = "127.0.0.1",
        create_route: bool = True,
    ) -> Dict[str, Any]:
        existing_subdomains = await self.get_existing_subdomains()

        prompt = f"""You are an expert DevOps and Homelab engineer.
Analyze the following docker-compose YAML configuration for stack '{stack_name}'.

Compose content:
```yaml
{compose_yaml[:4000]}
```

Existing occupied subdomains: {json.dumps(existing_subdomains)}

Generate metadata for this service:
1. "name": Clean human-readable title (e.g. "Jellyfin Media", "Uptime Kuma", "Grafana")
2. "type": One of: "multimedia", "tools", "networking", "infrastructure", "misc"
3. "description": A concise, friendly one-line description (under 80 chars)
4. "port": The primary host-mapped port number exposed to the host network (e.g. if ports is "8085:80", return 8085; if "3000:3000", return 3000; if only single port "8080", return 8080). Must be integer.
5. "scheme": "http" or "https" (almost always "http" for container origins)
6. "suggested_subdomains": Array of 3-4 clean, catchy subdomain candidates in lowercase (e.g. ["jellyfin", "stream", "media"]). DO NOT use any subdomain from the existing list.
7. "icon": Appropriate Lucide icon name matching the category (choose from: Music, Radio, Tv, Film, Cloud, Code, HardDrive, Network, Globe, Server, ShieldCheck, Activity, Database, Terminal, Box, Wrench)
8. "color": Hex color code (e.g. #dfb28f, #96c2e2, #9ed2bf, #e4a4a7, #9ab3e1)

Output strictly valid JSON with these keys."""

        ai_res = await gemini.generate_json(
            prompt=prompt,
            system_instruction="You are a precise JSON-only generator for homelab service metadata.",
        )
        data = ai_res["data"]

        # Pick the first available subdomain candidate
        candidates = data.get("suggested_subdomains", [stack_name.lower()])
        chosen_subdomain = None
        for c in candidates:
            clean = re.sub(r"[^a-z0-9-]", "", c.lower().strip())
            if clean and clean not in existing_subdomains:
                chosen_subdomain = clean
                break

        if not chosen_subdomain:
            chosen_subdomain = f"{stack_name.lower()}-app"

        # Deterministically extract host-mapped port if defined in compose
        host_port = None
        for line in compose_yaml.splitlines():
            sline = line.strip()
            if sline.startswith("-"):
                m = re.search(r'["\']?(?:(?:\d{1,3}\.){3}\d{1,3}:)?(\d{2,5}):\d{1,5}(?:/(?:tcp|udp))?["\']?', sline)
                if m:
                    try:
                        p_val = int(m.group(1))
                        if 1 <= p_val <= 65535:
                            host_port = p_val
                            break
                    except ValueError:
                        pass

        service_port = host_port if host_port else int(data.get("port", 8080))
        service_scheme = data.get("scheme", "http").lower()
        public_url = f"https://{chosen_subdomain}.{config.DOMAIN}"

        # Generate standard pve.toml content
        pve_toml_content = f"""[service]
runtime = "docker"
name = "{data.get('name', stack_name.title())}"
type = "{data.get('type', 'misc')}"
description = "{data.get('description', '')}"
url = "{public_url}"
icon = "{data.get('icon', 'Box')}"
color = "{data.get('color', '#96c2e2')}"
check_url = "{public_url}"
enabled = true
"""

        route_payload = None
        if create_route:
            route_payload = {
                "action": "create_route",
                "name": chosen_subdomain,
                "host": host_ip,
                "port": service_port,
                "scheme": service_scheme,
            }

        return {
            "stack_name": stack_name,
            "chosen_subdomain": chosen_subdomain,
            "subdomain_candidates": candidates,
            "public_url": public_url,
            "port": service_port,
            "scheme": service_scheme,
            "pve_toml": pve_toml_content,
            "parsed_metadata": data,
            "route_action_payload": route_payload,
            "ai_model_used": ai_res["model"],
            "key_used": ai_res["key"],
        }

pve_service = PveService()
