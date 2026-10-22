import asyncio
import datetime as dt
import os
import unittest
from unittest.mock import AsyncMock, patch
os.environ["RS_SERVICE_TOKEN"]="s"*32
from fastapi.testclient import TestClient
from app.main import app
from app.services.pve_service import parse_compose, Metadata, manifest, pve_service
from app.services.telemetry import TelemetryError
from app.services.rankings_service import rankings_service
from app.services.diagnostics_service import diagnostics_service

class RegressionTests(unittest.TestCase):
    def test_key_failover_does_not_expose_credentials(self):
        import httpx
        from app.gemini_client import GeminiClient
        client=AsyncMock()
        client.__aenter__.return_value=client
        client.__aexit__.return_value=False
        client.post.side_effect=[httpx.Response(403),httpx.Response(200,json={"candidates":[{"content":{"parts":[{"text":"ok"}]}}]})]
        async def check():
            with patch("app.gemini_client.config.get_api_keys",return_value=["bad-fixture","good-fixture"]), patch("app.gemini_client.config.get_fallback_models",return_value=[]), patch("app.gemini_client.httpx.AsyncClient",return_value=client), patch("app.gemini_client.asyncio.sleep",AsyncMock()):
                result=await GeminiClient().generate_content("Synthetic test")
                self.assertEqual(result["text"],"ok")
                self.assertEqual(client.post.await_count,2)
                self.assertNotIn("fixture",str(result))
        asyncio.run(check())
    def test_private_boundary(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/rankings").status_code,401)
            self.assertEqual(client.get("/healthz").status_code,200)
            with patch("app.services.rankings_service.telemetry.get",AsyncMock(side_effect=TelemetryError("Unavailable"))):
                result=client.get("/api/rankings",headers={"X-Service-Token":"s"*32})
                self.assertEqual(result.status_code,503)
                self.assertFalse(result.json()["available"])
    def test_compose_ports(self):
        _,options=parse_compose('services:\n  web:\n    ports:\n      - "[::1]:8085:80/tcp"\n      - target: 80\n        published: 8086\n      - "53:53/udp"\n      - "80"\n')
        self.assertEqual([o["port"] for o in options],[8085,8086])
        with self.assertRaises(ValueError): parse_compose("not-compose")
    def test_toml_escaping(self):
        import tomllib
        meta=Metadata(name='Quoted " name',description='line\n[evil]')
        parsed=tomllib.loads(manifest(meta,"https://app.test","web"))
        self.assertEqual(parsed["service"]["name"],meta.name)
        self.assertNotIn("evil",parsed)
    def test_healthy_and_rankings(self):
        status={"updated":dt.datetime.now(dt.timezone.utc).isoformat(),"host":{},"lxcs":[{"id":100,"name":"Alpine","containers":[{"name":"same","state":"exited","memory_text":"2MiB / 1GiB","memory_percent":90,"cpu":1}]},{"id":101,"name":"Debian","containers":[{"name":"same","state":"running","memory_text":"4MiB / 1GiB","memory_percent":10,"cpu":2}]}]}
        with patch("app.services.rankings_service.telemetry.get",AsyncMock(return_value=status)):
            result=asyncio.run(rankings_service.get_performance_rankings())
            self.assertEqual(result["top_memory"][0]["lxc_id"],101)
            self.assertEqual(len(result["top_memory"]),2)
        with patch("app.services.diagnostics_service.telemetry.get",AsyncMock(return_value=status)):
            result=asyncio.run(diagnostics_service.run_diagnostics())
            self.assertEqual(result[0]["severity"],"healthy")
    def test_ambiguous_ports_and_loopback(self):
        async def check():
            with self.assertRaises(ValueError):
                await pve_service.analyze_and_generate('services:\n  web:\n    ports: ["8081:80", "8082:81"]\n',"test")
            status={"lxcs":[{"id":100,"name":"Alpine","ip":"192.168.1.51"}],"routes":[]}
            with patch("app.services.pve_service.telemetry.get",AsyncMock(return_value=status)):
                with self.assertRaises(ValueError):
                    await pve_service.analyze_and_generate('services:\n  web:\n    ports: ["8081:80"]\n',"test",100,"127.0.0.1")
        asyncio.run(check())
if __name__=="__main__": unittest.main()
