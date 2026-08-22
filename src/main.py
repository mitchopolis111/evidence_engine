from fastapi import FastAPI

from .case_intelligence_router import router as case_intelligence_router
from .router import router

app = FastAPI(
    title="Mitchopolis Evidence AI Engine",
    version="1.1.0",
)

app.include_router(router, prefix="/api/evidence", tags=["Evidence"])
app.include_router(case_intelligence_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "evidence_engine"}
