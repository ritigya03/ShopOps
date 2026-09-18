from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.observability.logging_setup import add_request_logging_middleware, configure_logging
from app.routes import router

configure_logging()

app = FastAPI(title="ShopOps AI Backend")
add_request_logging_middleware(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
