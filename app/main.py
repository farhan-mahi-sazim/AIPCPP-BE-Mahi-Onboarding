from fastapi import FastAPI
from app.modules.content.routes import router as content_router

app = FastAPI(
    title="AI-Powered Content Processing Pipeline",
    description="API for ingesting and processing content with AI",
    version="0.1.0",
)

app.include_router(content_router, prefix="/api/v1/content", tags=["Content"])

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
