import asyncio
import hmac
import time
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.api.routes import router
from app.config import config
from app.services.telemetry import TelemetryError
app=FastAPI(title="Prox-Agent",version="2.0.0",docs_url=None,redoc_url=None,openapi_url=None)
slots=asyncio.Semaphore(4)
attempts=[]
@app.on_event("startup")
async def startup():
    if len(config.SERVICE_TOKEN)<32:
        raise RuntimeError("RS_SERVICE_TOKEN must be configured")
@app.middleware("http")
async def boundary(request:Request, call_next):
    if request.url.path=="/healthz":
        return JSONResponse({"ok":True,"service":"prox-agent"})
    if not config.SERVICE_TOKEN or not hmac.compare_digest(request.headers.get("x-service-token",""),config.SERVICE_TOKEN):
        return JSONResponse({"error":"Unauthorized"},401)
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>65536:
            return JSONResponse({"error":"Request too large"},413)
    request._body=bytes(body)
    if request.method not in ("GET","POST"):
        return JSONResponse({"error":"Method not allowed"},405)
    if request.url.path!="/api/health":
        now=time.monotonic();attempts[:]=[t for t in attempts if now-t<60]
        if len(attempts)>=30:
            return JSONResponse({"error":"AI request limit reached; retry shortly"},429)
        attempts.append(now)
    try:
        async with asyncio.timeout(32):
            async with slots:
                return await call_next(request)
    except TimeoutError:
        return JSONResponse({"error":"Analysis timed out"},504)
@app.exception_handler(TelemetryError)
async def telemetry_error(request,exc):
    return JSONResponse({"error":str(exc),"available":False},503)
@app.exception_handler(Exception)
async def internal_error(request,exc):
    return JSONResponse({"error":"Analysis unavailable; local service error"},500)
app.include_router(router,prefix="/api")
