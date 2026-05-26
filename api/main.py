"""FastAPI application entry point."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from configs.defaults import EMBEDDING_MODEL
from src.indexer import load_embedder
from api.state import embedder_state
from api.routes import compare, documents, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the embedding model once at startup, release on shutdown."""
    logger.info("Loading embedding model at startup…")
    embedder_state["embedder"] = load_embedder(
        EMBEDDING_MODEL,
        hf_token=os.getenv("HF_TOKEN"),
    )
    logger.info("Embedding model ready.")
    yield
    logger.info("API shutting down.")


app = FastAPI(
    title="Legal Document Comparison API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(compare.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(health.router, prefix="/api")
