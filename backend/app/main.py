import os
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.database import close_database, connect_database
from app.seed import seed_demo_data


def create_app(connector: Callable = connect_database, seed_data: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        client, collection = await connector()
        application.state.mongo_client = client
        application.state.leads = collection
        try:
            if seed_data:
                await seed_demo_data(collection)
            yield
        finally:
            await close_database(client)

    application = FastAPI(title="SaaSquatch Lead Intelligence API", version="1.0.0", lifespan=lifespan)
    origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router)
    return application


app = create_app()
