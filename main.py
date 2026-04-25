from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import gateway_router

app = FastAPI(title="irvinbot-gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gateway_router.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "gateway"}
