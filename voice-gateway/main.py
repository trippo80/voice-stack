import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from websocket_handler import ws_handler
from routes import router as http_router
from wyoming import start_wyoming_servers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Set DEBUG level for websocket_handler to see chunk-level logs
# logging.getLogger("websocket_handler").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - start Wyoming servers on startup."""
    # Start Wyoming servers in the background
    wyoming_task = asyncio.create_task(start_wyoming_servers())
    logger.info("Wyoming servers starting...")

    yield

    # Cleanup on shutdown
    wyoming_task.cancel()
    try:
        await wyoming_task
    except asyncio.CancelledError:
        pass
    logger.info("Wyoming servers stopped")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(http_router)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_handler(ws)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5002)

