"""Local HTTP server to receive credentials from browser redirect."""

import asyncio
import base64
import hashlib
import json

from aiohttp import web
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class CallbackServer:
    """Local HTTP server to receive credentials from nor-auth.

    Attributes:
        port: HTTP server port.
        session_secret: Secret used for AES-256 decryption.
        credentials: Received credentials, None until callback succeeds.
    """

    def __init__(self, port: int, session_secret: str):
        self.port = port
        self.session_secret = session_secret
        self.credentials: list[dict] | None = None
        self._app = web.Application()
        self._app.router.add_get("/callback", self._handle_callback)
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        """Start the callback server."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "localhost", self.port)
        await site.start()

    async def stop(self) -> None:
        """Stop the callback server."""
        if self._runner:
            await self._runner.cleanup()

    async def __aenter__(self) -> "CallbackServer":
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop()

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """Handle credential callback from nor-auth.

        Args:
            request: HTTP request from callback endpoint.

        Returns:
            400 response if credentials missing or decryption failed,
            otherwise redirects to success URL.
        """
        encrypted = request.query.get("credentials")
        if not encrypted:
            return web.Response(text="Missing credentials", status=400)

        try:
            raw_credentials = self._decrypt(encrypted)
            self.credentials = raw_credentials.get("resources")
            raise web.HTTPFound(location=raw_credentials["successUrl"])
        except web.HTTPFound:
            raise
        except Exception as e:
            return web.Response(text=f"Decryption failed: {e}", status=400)

    def _decrypt(self, encrypted: str) -> dict:
        """Decrypt credentials using AES-256-CBC.

        Args:
            encrypted: Base64url-encoded IV + ciphertext.

        Returns:
            Decrypted JSON object containing resources and successUrl.

        Format: base64url(IV + ciphertext)
        Key: SHA-256(session_secret)
        """
        # Add padding - Node base64url omits '='
        encrypted += "=" * (-len(encrypted) % 4)
        raw = base64.urlsafe_b64decode(encrypted)
        iv = raw[:16]
        ciphertext = raw[16:]

        key = hashlib.sha256(self.session_secret.encode()).digest()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()

        padded = decryptor.update(ciphertext) + decryptor.finalize()

        # Remove PKCS7 padding
        pad_len = padded[-1]
        plaintext = padded[:-pad_len]

        return json.loads(plaintext.decode())

    async def wait_for_credentials(self, timeout: float = 300) -> list[dict] | None:
        """Wait for credentials with timeout.

        Args:
            timeout: Maximum seconds to wait. Defaults to 300.

        Returns:
            Received credentials list, or None if timeout reached.
        """
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            if self.credentials:
                return self.credentials
            await asyncio.sleep(0.5)
        return None
