from fastapi import FastAPI

from .routers import auth

app = FastAPI(title="Sabor da Terra API")

app.include_router(auth.router)
