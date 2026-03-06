import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class AnonexAuth(AuthBase):
    """
    Auth class for AnonEx API.

    REST authentication uses HTTP Basic Auth (api_key:api_secret) OR
    HMAC-SHA256 signed requests with headers:
      - x-api-key: the API key
      - x-api-nonce: a unique nonce (timestamp-based)
      - x-api-sign: HMAC-SHA256(apiKey + fullUrl + bodyString + nonce, apiSecret)

    WebSocket authentication uses JSON-RPC "login" method with either:
      - algo: "basic", pKey: apiKey, sKey: apiSecret
      - algo: "hs256", pKey: apiKey, nonce: nonce, signature: HMAC-SHA256(nonce, apiSecret)
    """

    def __init__(self, api_key: str, secret_key: str, time_provider: Optional[TimeSynchronizer] = None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds HMAC-SHA256 signature headers to the request for authenticated interactions.
        Uses the x-api-key / x-api-nonce / x-api-sign header scheme.
        """
        headers = dict(request.headers) if request.headers else {}

        nonce = str(int(time.time() * 1000))

        url = request.url or ""
        body_string = ""
        if request.method == RESTMethod.POST and request.data:
            body_string = request.data if isinstance(request.data, str) else ""

        # Signature: HMAC-SHA256(apiKey + url + bodyString + nonce, apiSecret)
        sign_payload = self.api_key + url + body_string + nonce
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            sign_payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        headers["x-api-key"] = self.api_key
        headers["x-api-nonce"] = nonce
        headers["x-api-sign"] = signature

        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        WebSocket authentication is handled separately via the login method.
        This is a pass-through.
        """
        return request

    def get_ws_login_params_basic(self) -> Dict[str, Any]:
        """Generate params for WebSocket login using basic auth."""
        return {
            "algo": "basic",
            "pKey": self.api_key,
            "sKey": self.secret_key,
        }

    def get_ws_login_params_hmac(self) -> Dict[str, Any]:
        """Generate params for WebSocket login using HMAC-SHA256."""
        nonce = str(int(time.time() * 1000))
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            nonce.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return {
            "algo": "hs256",
            "pKey": self.api_key,
            "nonce": nonce,
            "signature": signature,
        }

    def header_for_authentication(self) -> Dict[str, str]:
        """Generate Basic Auth header as an alternative auth method."""
        import base64
        credentials = base64.b64encode(f"{self.api_key}:{self.secret_key}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}
