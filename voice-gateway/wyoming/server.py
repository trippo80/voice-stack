"""
Wyoming TCP server runner.

Starts Wyoming-compatible TCP servers for TTS and ASR services.
"""

import asyncio
import logging

from config import (
    WYOMING_TTS_ENABLED, WYOMING_TTS_PORT,
    WYOMING_ASR_ENABLED, WYOMING_ASR_PORT,
)
from .tts_service import handle_tts_client
from .asr_service import handle_asr_client
from .zeroconf import register_wyoming_services, stop_zeroconf

logger = logging.getLogger(__name__)


async def run_wyoming_tts_server(host: str = "0.0.0.0", port: int = None):
    """Run the Wyoming TTS server."""
    if port is None:
        port = WYOMING_TTS_PORT

    server = await asyncio.start_server(
        handle_tts_client,
        host,
        port,
    )

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    logger.info(f"Wyoming TTS server listening on {addrs}")

    async with server:
        await server.serve_forever()


async def run_wyoming_asr_server(host: str = "0.0.0.0", port: int = None):
    """Run the Wyoming ASR server."""
    if port is None:
        port = WYOMING_ASR_PORT

    server = await asyncio.start_server(
        handle_asr_client,
        host,
        port,
    )

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    logger.info(f"Wyoming ASR server listening on {addrs}")

    async with server:
        await server.serve_forever()


async def start_wyoming_servers():
    """Start all enabled Wyoming servers."""
    tasks = []

    if WYOMING_TTS_ENABLED:
        logger.info(f"Starting Wyoming TTS server on port {WYOMING_TTS_PORT}")
        tasks.append(asyncio.create_task(run_wyoming_tts_server()))
    else:
        logger.info("Wyoming TTS server disabled")

    if WYOMING_ASR_ENABLED:
        logger.info(f"Starting Wyoming ASR server on port {WYOMING_ASR_PORT}")
        tasks.append(asyncio.create_task(run_wyoming_asr_server()))
    else:
        logger.info("Wyoming ASR server disabled")

    # Register services with Zeroconf for Home Assistant auto-discovery
    if WYOMING_TTS_ENABLED or WYOMING_ASR_ENABLED:
        try:
            await register_wyoming_services(
                tts_enabled=WYOMING_TTS_ENABLED,
                tts_port=WYOMING_TTS_PORT,
                asr_enabled=WYOMING_ASR_ENABLED,
                asr_port=WYOMING_ASR_PORT,
            )
        except Exception as e:
            logger.warning(f"Failed to register Zeroconf services: {e}")

    if tasks:
        # Wait for all servers (they run forever unless cancelled)
        await asyncio.gather(*tasks, return_exceptions=True)


async def stop_wyoming_servers():
    """Stop Wyoming servers and cleanup Zeroconf."""
    await stop_zeroconf()
