from fastapi import FastAPI
from .router import router
app = FastAPI(
    title="Mitchopolis Evidence AI Engine",
    version="1.0.0"
)

app.include_router(router, prefix="/api/evidence", tags=["Evidence"])

@app.get("/health")
def health():
    return {"status": "ok", "service": "evidence_engine"}
