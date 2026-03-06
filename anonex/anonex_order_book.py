from typing import Dict, Optional

from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType


class AnonexOrderBook(OrderBook):

    @classmethod
    def snapshot_message_from_exchange(cls,
                                       msg: Dict[str, any],
                                       timestamp: float,
                                       metadata: Optional[Dict] = None) -> OrderBookMessage:
        """
        Creates a snapshot message from the AnonEx order book snapshot.
        AnonEx orderbook response format:
        {
            "marketid": "...",
            "symbol": "BTC/USDT",
            "timestamp": 1234567890,
            "sequence": "123",
            "bids": [{"price": "50000", "quantity": "1.5"}, ...],
            "asks": [{"price": "50001", "quantity": "0.5"}, ...]
        }
        """
        if metadata:
            msg.update(metadata)

        # Convert AnonEx bid/ask format to Hummingbot format [[price, quantity], ...]
        bids = [[entry["price"], entry["quantity"]] for entry in msg.get("bids", [])]
        asks = [[entry["price"], entry["quantity"]] for entry in msg.get("asks", [])]

        return OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
            "trading_pair": msg["trading_pair"],
            "update_id": msg.get("sequence", msg.get("timestamp", 0)),
            "bids": bids,
            "asks": asks
        }, timestamp=timestamp)

    @classmethod
    def diff_message_from_exchange(cls,
                                   msg: Dict[str, any],
                                   timestamp: Optional[float] = None,
                                   metadata: Optional[Dict] = None) -> OrderBookMessage:
        """
        Creates a diff message from AnonEx WebSocket orderbook updates.
        AnonEx WS orderbook messages come via wss_orderfeed_ channel as JSON-RPC:
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
        if metadata:
            msg.update(metadata)

        bids = msg.get("bids", [])
        asks = msg.get("asks", [])

        # Convert to [[price, quantity], ...] if needed
        if bids and isinstance(bids[0], dict):
            bids = [[b["price"], b["quantity"]] for b in bids]
        if asks and isinstance(asks[0], dict):
            asks = [[a["price"], a["quantity"]] for a in asks]

        return OrderBookMessage(OrderBookMessageType.DIFF, {
            "trading_pair": msg["trading_pair"],
            "first_update_id": msg.get("sequence", 0),
            "update_id": msg.get("sequence", 0),
            "bids": bids,
            "asks": asks
        }, timestamp=timestamp)

    @classmethod
    def trade_message_from_exchange(cls, msg: Dict[str, any], metadata: Optional[Dict] = None):
        """
        Creates a trade message from AnonEx trade events.
        AnonEx WS trade messages come via wss_tradefeed_ channel:
        {
            "jsonrpc": "2.0",
            "method": "updateTrades",
            "params": {
                "data": [{
                    "id": "...",
                    "price": "50000.00",
                    "quantity": "0.1",
                    "timestamp": "2024-01-01T00:00:00.000Z",
                    "side": "buy"
                }],
                "symbol": "BTC/USDT",
                "sequence": "124"
            }
        }
        """
        if metadata:
            msg.update(metadata)
        ts = msg.get("timestamp", 0)
        if isinstance(ts, str):
            from datetime import datetime
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except (ValueError, AttributeError):
                import time
                ts = time.time()

        trade_type = float(TradeType.BUY.value) if msg.get("side", "buy") == "buy" else float(TradeType.SELL.value)

        return OrderBookMessage(OrderBookMessageType.TRADE, {
            "trading_pair": msg["trading_pair"],
            "trade_type": trade_type,
            "trade_id": msg.get("id", ""),
            "update_id": ts,
            "price": msg.get("price", "0"),
            "amount": msg.get("quantity", msg.get("baseVolume", "0"))
        }, timestamp=ts)
