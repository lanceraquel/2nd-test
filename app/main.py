from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_health import router as health_router
from app.api.routes_tasks import router as tasks_router
from app.database import init_db
from app.logging_config import configure_logging
 
configure_logging()
 
app = FastAPI(
    title="Atlas Research Pipeline",
    description="OpenAI-based staged research pipeline for Railway deployment.",
    version="0.1.0",
)
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",            # Vite dev server
        "http://localhost:4173",            # Vite preview
        "https://*.up.railway.app",         # Any Railway-deployed dashboard
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
@app.get("/")
def read_root():
    return {
        "message": "Atlas Research Pipeline API",
        "status": "running",
        "version": "0.1.0"
    }
 
@app.on_event("startup")
def on_startup() -> None:
    init_db()
 
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(tasks_router)
