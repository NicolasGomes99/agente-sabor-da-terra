from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_cors_allowed_origins
from .routers import auth, chat

app = FastAPI(title="Sabor da Terra API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(chat.router)