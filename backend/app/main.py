import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.match_timing_log import init_match_timing_log
from app.routes import router


load_dotenv()
init_match_timing_log()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Mongo ping + occupation JSON + WA lookup once at startup so /match does not pay cold-connection cost each time."""
    from app.database import warmup_on_startup

    await warmup_on_startup()
    yield


app = FastAPI(title="Matching Service", lifespan=lifespan)

logging.basicConfig(level=logging.INFO)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0", port=8000)
