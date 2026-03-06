import asyncio
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.anonex import anonex_constants as CONSTANTS
from hummingbot.connector.exchange.anonex.anonex_auth import AnonexAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest, WSResponse
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.anonex.anonex_exchange import AnonexExchange


class AnonexAPIUserStreamDataSource(UserStreamTrackerDataSource):
    """
    Manages the WebSocket connection for user-specific data (balances, orders).

    AnonEx WebSocket uses JSON-RPC 2.0 protocol. Authentication flow:
    1. Connect to WSS_URL
    2. Send login: {"method": "login", "params": {"algo": "hs256", "pKey": key, "nonce": n, "signature": sig}, "id": 1}
    3. Receive: {"jsonrpc": "2.0", "result": true, "id": 1}
    4. Subscribe to balance updates: {"method": "subscribeBalances", "params": {}, "id": 2}
    5. Balance updates arrive as: {"jsonrpc": "2.0", "method": "currentBalances", "result": [...]}
    """

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: AnonexAuth,
                 trading_pairs: List[str],
                 connector: 'AnonexExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__()
        self._auth: AnonexAuth = auth
        self._domain = domain
        self._api_factory = api_factory
        self._connector = connector
        self._trading_pairs = trading_pairs

    async def _get_ws_assistant(self) -> WSAssistant:
        return await self._api_factory.get_ws_assistant()

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws = await self._get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL,
                         ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Authenticates and subscribes to user-specific channels.
        """
        try:
            # Step 1: Login via HMAC
            login_params = self._auth.get_ws_login_params_hmac()
            login_payload = {
                "method": CONSTANTS.WS_METHOD_LOGIN,
                "params": login_params,
                "id": 1
            }
            await websocket_assistant.send(WSJSONRequest(payload=login_payload))

            # Wait for login response
            response: WSResponse = await websocket_assistant.receive()
            data = response.data
            if isinstance(data, str):
                data = json.loads(data)

            if not isinstance(data, dict) or data.get("result") is not True:
                raise IOError(f"AnonEx WebSocket login failed (response: {data})")

            self.logger().info("Successfully authenticated AnonEx WebSocket connection")

            # Step 2: Subscribe to balance updates
            balance_payload = {
                "method": CONSTANTS.WS_METHOD_SUBSCRIBE_BALANCES,
                "params": {},
                "id": 2
            }
            await websocket_assistant.send(WSJSONRequest(payload=balance_payload))

            self.logger().info("Subscribed to AnonEx user balance stream")

        except IOError:
            raise
        except Exception:
            self.logger().exception("Unexpected error subscribing to AnonEx user data stream")
            raise

    async def _process_event_message(self, event_message: Dict[str, Any], queue):
        """
        Process incoming user stream events and forward relevant ones.

        Relevant events:
        - currentBalances: balance snapshot/update
          {"jsonrpc": "2.0", "method": "currentBalances", "result": [{"ticker": "BTC", "available": "1.0", "held": "0.5"}]}
        - balanceUpdate: individual balance change
          {"jsonrpc": "2.0", "method": "balanceUpdate", "params": {"data": [...]}}
        """
        if not isinstance(event_message, dict) or len(event_message) == 0:
            return

        # Filter out subscription confirmations (have "id" and "result")
        if "id" in event_message and "error" not in event_message and "method" not in event_message:
            return

        # Handle pong messages
        method = event_message.get("method", "")
        if method == "pong":
            return

        # Forward balance updates and order updates
        if method in ("currentBalances", "balanceUpdate", "orderUpdate", "tradeUpdate"):
            queue.put_nowait(event_message)

    async def _on_user_stream_interruption(self, websocket_assistant: Optional[WSAssistant]):
        if websocket_assistant:
            await websocket_assistant.disconnect()
