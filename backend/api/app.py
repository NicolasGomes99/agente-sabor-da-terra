
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_cors_allowed_origins
from .routers import auth, chat, document

fastapi_app = FastAPI(title="Sabor da Terra API")

fastapi_app.include_router(auth.router)
fastapi_app.include_router(chat.router)
fastapi_app.include_router(document.router)

app = CORSMiddleware(
    fastapi_app,
    allow_origins=get_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
    expose_headers=["Content-Disposition"],
)