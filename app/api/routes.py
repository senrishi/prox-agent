from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from app.services.pve_service import pve_service
from app.services.events_service import events_service
from app.services.diagnostics_service import diagnostics_service
from app.services.rankings_service import rankings_service
from app.services.telemetry import telemetry, TelemetryError
router=APIRouter()
class AnalyzeStackRequest(BaseModel):
    compose_yaml: str=Field(min_length=1,max_length=60000)
    stack_name: str=Field(min_length=1,max_length=63)
    lxc_id: int=Field(default=100,gt=0)
    host_ip: Optional[str]=None
    create_route: bool=True
    service_name: Optional[str]=None
    published_port: Optional[int]=Field(default=None,ge=1,le=65535)
@router.get("/health")
async def health():
    await telemetry.get()
    return {"ok":True,"telemetry":"available"}
@router.post("/analyze-stack")
async def analyze(req:AnalyzeStackRequest):
    try:
        return await pve_service.analyze_and_generate(**req.model_dump())
    except ValueError as e:
        raise HTTPException(422,str(e)) from None
@router.get("/events")
async def events(limit:int=Query(30,ge=1,le=100)):
    status=await telemetry.get()
    data=await events_service.get_major_events(limit)
    return {"ok":True,"events":data,"count":len(data),"updated":status["updated"],"source":"Proxmox task inventory"}
@router.get("/diagnostics")
async def diagnostics():
    data=await diagnostics_service.run_diagnostics()
    return {"ok":True,"diagnostics":data,"count":len([d for d in data if d['severity']!='healthy'])}
@router.get("/rankings")
async def rankings():
    return {"ok":True,**await rankings_service.get_performance_rankings()}
