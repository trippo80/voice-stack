from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from websocket_handler import ws_handler
from routes import router as http_router

app = FastAPI()
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

