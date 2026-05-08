import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config.db import engine, init_db
from app.modules.content import routes as content_routes
from app.modules.healthcheck import routes as healthcheck_routes

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


app.include_router(healthcheck_routes.router, prefix="/api/v1")
app.include_router(content_routes.router, prefix="/api/v1/content", tags=["Content"])
