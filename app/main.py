import logging
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config.db import engine, init_db
from app.modules.content import routes as content_routes
from app.modules.healthcheck import routes as healthcheck_routes
from app.modules.search import routes as search_routes
from app.modules.versions import routes as version_routes

# Placeholder imports for future modules
# from app.modules.auth import routes as auth_routes
# from app.modules.users import routes as user_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up...")
    await init_db()
    yield
    logger.info("Shutting down...")
    await engine.dispose()


app = FastAPI(
    title="AI-Powered Content Processing Pipeline",
    description="API for ingesting and processing content with AI",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", exc, "".join(traceback.format_exc()))
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


app.include_router(healthcheck_routes.router, prefix="/api/v1")
app.include_router(content_routes.router, prefix="/api/v1/content", tags=["Content"])
app.include_router(version_routes.router, prefix="/api/v1/versions", tags=["Versions"])
app.include_router(search_routes.router, prefix="/api/v1", tags=["Search"])
