from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import get_settings
from app.db.migrate import ensure_columns
from app.db.session import Base, engine
from app import models  # noqa: F401 - registers ORM models on Base before create_all

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Simple table creation for now — swap for Alembic migrations once the
    # schema needs to evolve without dropping data (requirements.txt already
    # includes alembic for that). create_all never ALTERs, so ensure_columns
    # covers the one case that keeps coming up: a new nullable column added to
    # a model whose table an older database already has.
    Base.metadata.create_all(bind=engine)
    ensure_columns(engine, Base.metadata)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
