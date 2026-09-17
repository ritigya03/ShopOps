from fastapi import FastAPI

from app.routes import router

app = FastAPI(title="ShopOps AI Backend")
app.include_router(router)
