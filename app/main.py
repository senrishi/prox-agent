from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.config import config

app = FastAPI(
    title="Prox-Agent",
    description="Intelligent Homelab AI Assistant powered by Google Gemini API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {
        "service": "prox-agent",
        "description": "Proxmox & Docker Homelab AI Intelligence Service",
        "docs": "/docs",
        "health": "/api/health",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.PORT, reload=True)
