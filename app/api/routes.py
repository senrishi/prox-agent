from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import config
from app.services.pve_service import pve_service
from app.services.events_service import events_service
from app.services.diagnostics_service import diagnostics_service
from app.services.rankings_service import rankings_service

router = APIRouter()

class AnalyzeStackRequest(BaseModel):
    compose_yaml: str
    stack_name: str
    lxc_id: Optional[int] = 100
    host_ip: Optional[str] = "127.0.0.1"
    create_route: Optional[bool] = True

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    keys = config.get_api_keys()
    return {
        "status": "ok",
        "service": "prox-agent",
        "api_keys_configured": len(keys),
        "primary_model": config.PRIMARY_MODEL,
        "fallback_models": config.get_fallback_models(),
    }

@router.post("/analyze-stack")
async def analyze_stack(req: AnalyzeStackRequest) -> Dict[str, Any]:
    if not req.compose_yaml.strip():
        raise HTTPException(status_code=400, detail="compose_yaml content cannot be empty")
    try:
        res = await pve_service.analyze_and_generate(
            compose_yaml=req.compose_yaml,
            stack_name=req.stack_name,
            lxc_id=req.lxc_id or 100,
            host_ip=req.host_ip or "127.0.0.1",
            create_route=req.create_route if req.create_route is not None else True,
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/events")
async def get_events(limit: int = 30) -> Dict[str, Any]:
    try:
        events = await events_service.get_major_events(limit=limit)
        return {
            "ok": True,
            "count": len(events),
            "events": events,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/diagnostics")
async def get_diagnostics() -> Dict[str, Any]:
    try:
        diagnostics = await diagnostics_service.run_diagnostics()
        return {
            "ok": True,
            "count": len(diagnostics),
            "diagnostics": diagnostics,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rankings")
async def get_rankings() -> Dict[str, Any]:
    try:
        data = await rankings_service.get_performance_rankings()
        return {
            "ok": True,
            **data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
