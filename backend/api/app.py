from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_cors_allowed_origins
from .routers import auth, document

app = FastAPI(title="Sabor da Terra API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
)

app.include_router(auth.router)
app.include_router(document.router)
