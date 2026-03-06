import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.anonex import anonex_constants as CONSTANTS, anonex_web_utils as web_utils
from hummingbot.connector.exchange.anonex.anonex_order_book import AnonexOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.anonex.anonex_exchange import AnonexExchange

# AnonEx WebSocket uses JSON-RPC 2.0 protocol.
# Channels are subscribed via method calls like subscribeTrades, subscribeOrderbook.
# Messages come back on Redis pub/sub channels: wss_tradefeed_{symbol}, wss_orderfeed_{symbol}.

TRADE_CHANNEL_SUFFIX = "tradefeed"
ORDERBOOK_CHANNEL_SUFFIX = "orderfeed"


class AnonexAPIOrderBookDataSource(OrderBookTrackerDataSource):
    HEARTBEAT_TIME_INTERVAL = 30.0
    ONE_HOUR = 60 * 60

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 trading_pairs: List[str],
                 connector: 'AnonexExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__(trading_pairs)
        self._connector = connector
        self._domain = domain
        self._api_factory = api_factory
        self._trade_messages_queue_key = TRADE_CHANNEL_SUFFIX
        self._diff_messages_queue_key = ORDERBOOK_CHANNEL_SUFFIX

    async def get_last_traded_prices(self,
                                     trading_pairs: List[str],
                                     domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Retrieves the full order book from AnonEx REST API.
        GET /api/v2/market/orderbook?symbol=BTC/USDT&limit=500
        Response: { marketid, symbol, timestamp, sequence, bids: [{price, quantity}], asks: [{price, quantity}] }
        """
        symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        params = {
            "symbol": symbol,
            "limit": "500"
        }

        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(path_url=CONSTANTS.ORDERBOOK_PATH_URL, domain=self._domain),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.ORDERBOOK_PATH_URL,
        )
        return data

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to orderbook and trade channels for all trading pairs via AnonEx WebSocket.
        AnonEx uses JSON-RPC 2.0 protocol:
          {"method": "subscribeOrderbook", "params": {"symbol": "BTC/USDT"}, "id": 1}
          {"method": "subscribeTrades", "params": {"symbol": "BTC/USDT"}, "id": 2}
        """
        try:
            msg_id = 1
            for trading_pair in self._trading_pairs:
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)

                # Subscribe to orderbook
                ob_payload = {
                    "method": CONSTANTS.WS_METHOD_SUBSCRIBE_ORDERBOOK,
                    "params": {"symbol": symbol},
                    "id": msg_id
                }
                await ws.send(WSJSONRequest(payload=ob_payload))
                msg_id += 1

                # Subscribe to trades
                trade_payload = {
                    "method": CONSTANTS.WS_METHOD_SUBSCRIBE_TRADES,
                    "params": {"symbol": symbol},
                    "id": msg_id
                }
                await ws.send(WSJSONRequest(payload=trade_payload))
                msg_id += 1

            self.logger().info("Subscribed to public order book and trade channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error subscribing to order book and trade streams...",
                exc_info=True
            )
            raise

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL,
                         ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp: float = time.time()
        snapshot_msg: OrderBookMessage = AnonexOrderBook.snapshot_message_from_exchange(
            snapshot,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        Parse AnonEx WebSocket trade messages.
        AnonEx sends trade updates as JSON-RPC:
        {
            "jsonrpc": "2.0",
            "method": "updateTrades",
            "params": {
                "data": [{"id": "...", "price": "...", "quantity": "...", "timestamp": "...", "side": "buy"}],
                "symbol": "BTC/USDT",
                "sequence": "123"
            }
        }
        """
        method = raw_message.get("method", "")
        if method not in ("updateTrades", "snapshotTrades"):
            return

        params = raw_message.get("params", {})
        symbol = params.get("symbol", "")
        if not symbol:
            return

        try:
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=symbol)
        except KeyError:
            return

        trades = params.get("data", [])
        for trade in trades:
            trade_msg = AnonexOrderBook.trade_message_from_exchange(
                trade, {"trading_pair": trading_pair}
            )
            message_queue.put_nowait(trade_msg)

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        Parse AnonEx WebSocket orderbook updates.
        {
            "jsonrpc": "2.0",
            "method": "snapshotOrderbook" or "updateOrderbook",
            "params": {
                "data": {"bids": [...], "asks": [...]},
                "symbol": "BTC/USDT",
                "sequence": "123",
                "timestamp": 1234567890
            }
        }
        """
        method = raw_message.get("method", "")
        if method not in ("snapshotOrderbook", "updateOrderbook"):
            return

        params = raw_message.get("params", {})
        symbol = params.get("symbol", "")
        if not symbol:
            return

        try:
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=symbol)
        except KeyError:
            return

        data = params.get("data", {})
        data["trading_pair"] = trading_pair
        data["sequence"] = params.get("sequence", 0)

        order_book_message = AnonexOrderBook.diff_message_from_exchange(
            data, time.time(), {"trading_pair": trading_pair}
        )
        message_queue.put_nowait(order_book_message)

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        """
        Determines which queue to route the message to based on the JSON-RPC method.
        """
        method = event_message.get("method", "")
        if method in ("updateTrades", "snapshotTrades"):
            return self._trade_messages_queue_key
        elif method in ("snapshotOrderbook", "updateOrderbook"):
            return self._diff_messages_queue_key
        return ""
