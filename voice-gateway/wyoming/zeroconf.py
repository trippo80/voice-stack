"""
Zeroconf/mDNS service advertisement for Wyoming services.

Allows Home Assistant to auto-discover the Wyoming TTS and ASR services.
"""

import logging
import socket
from typing import Optional

from zeroconf import IPVersion
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

logger = logging.getLogger(__name__)

WYOMING_SERVICE_TYPE = "_wyoming._tcp.local."


def _get_local_ip() -> str:
    """Get the local IP address of this machine."""
    try:
        # Create a socket to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class WyomingZeroconf:
    """Manages Zeroconf advertisement for Wyoming services."""

    def __init__(self):
        self._zeroconf: Optional[AsyncZeroconf] = None
        self._services: list[AsyncServiceInfo] = []

    async def start(self):
        """Start the Zeroconf instance."""
        self._zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)
        logger.info("Zeroconf started")

    async def stop(self):
        """Stop Zeroconf and unregister all services."""
        if self._zeroconf:
            for service in self._services:
                try:
                    await self._zeroconf.async_unregister_service(service)
                    logger.info(f"Unregistered service: {service.name}")
                except Exception as e:
                    logger.warning(f"Error unregistering service: {e}")

            await self._zeroconf.async_close()
            self._zeroconf = None
            self._services.clear()
            logger.info("Zeroconf stopped")

    async def register_service(
        self,
        name: str,
        port: int,
        service_type: str = "tts",
        host: Optional[str] = None,
    ):
        """
        Register a Wyoming service for discovery.

        Args:
            name: Service name (e.g., "voice-gateway-tts")
            port: Port the service is listening on
            service_type: Type of service ("tts" or "asr")
            host: Host IP address (auto-detected if not provided)
        """
        if not self._zeroconf:
            logger.warning("Zeroconf not started, cannot register service")
            return

        if host is None:
            host = _get_local_ip()

        # Create service info
        service_name = f"{name}.{WYOMING_SERVICE_TYPE}"

        try:
            addresses = [socket.inet_aton(host)]
        except OSError:
            logger.warning(f"Invalid IP address: {host}, using 127.0.0.1")
            addresses = [socket.inet_aton("127.0.0.1")]

        properties = {
            "type": service_type,
        }

        service_info = AsyncServiceInfo(
            WYOMING_SERVICE_TYPE,
            service_name,
            addresses=addresses,
            port=port,
            properties=properties,
            server=f"{name}.local.",
        )

        try:
            await self._zeroconf.async_register_service(service_info)
            self._services.append(service_info)
            logger.info(f"Registered Wyoming {service_type} service: {name} at {host}:{port}")
        except Exception as e:
            logger.exception(f"Failed to register service {name}: {e}")


# Global instance
_zeroconf: Optional[WyomingZeroconf] = None


async def start_zeroconf() -> WyomingZeroconf:
    """Start the global Zeroconf instance."""
    global _zeroconf
    if _zeroconf is None:
        _zeroconf = WyomingZeroconf()
        await _zeroconf.start()
    return _zeroconf


async def stop_zeroconf():
    """Stop the global Zeroconf instance."""
    global _zeroconf
    if _zeroconf:
        await _zeroconf.stop()
        _zeroconf = None


async def register_wyoming_services(
    tts_enabled: bool,
    tts_port: int,
    asr_enabled: bool,
    asr_port: int,
    service_name: str = "voice-gateway",
):
    """Register Wyoming services for Home Assistant discovery."""
    zc = await start_zeroconf()

    if tts_enabled:
        await zc.register_service(
            name=f"{service_name}-tts",
            port=tts_port,
            service_type="tts",
        )

    if asr_enabled:
        await zc.register_service(
            name=f"{service_name}-asr",
            port=asr_port,
            service_type="asr",
        )
