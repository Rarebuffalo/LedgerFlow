from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router
from app.config import settings

app = FastAPI(
    title="LedgerLens API",
    description="Asynchronous Financial Data Processing & Intelligence Platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Set up CORS middleware for integration flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(api_router, tags=["API Endpoints"])

@app.get("/", tags=["Root"])
def read_root():
    return {
        "message": "Welcome to LedgerLens Financial Intelligence Platform API",
        "documentation": "/docs",
        "health": "/health"
    }
