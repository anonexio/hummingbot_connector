import asyncio
import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.anonex import (
    anonex_constants as CONSTANTS,
    anonex_utils,
    anonex_web_utils as web_utils,
)
from hummingbot.connector.exchange.anonex.anonex_api_order_book_data_source import AnonexAPIOrderBookDataSource
from hummingbot.connector.exchange.anonex.anonex_api_user_stream_data_source import AnonexAPIUserStreamDataSource
from hummingbot.connector.exchange.anonex.anonex_auth import AnonexAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


class AnonexExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0

    web_utils = web_utils

    def __init__(self,
                 anonex_api_key: str,
                 anonex_api_secret: str,
                 balance_asset_limit: Optional[Dict[str, Dict[str, Decimal]]] = None,
                 rate_limits_share_pct: Decimal = Decimal("100"),
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN,
                 ):
        self.api_key = anonex_api_key
        self.secret_key = anonex_api_secret
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        super().__init__(balance_asset_limit, rate_limits_share_pct)

    @staticmethod
    def anonex_order_type(order_type: OrderType) -> str:
        if order_type is OrderType.LIMIT or order_type is OrderType.LIMIT_MAKER:
            return CONSTANTS.ORDER_TYPE_LIMIT
        elif order_type is OrderType.MARKET:
            return CONSTANTS.ORDER_TYPE_MARKET
        return CONSTANTS.ORDER_TYPE_LIMIT

    @staticmethod
    def to_hb_order_type(anonex_type: str) -> OrderType:
        if anonex_type == CONSTANTS.ORDER_TYPE_MARKET:
            return OrderType.MARKET
        return OrderType.LIMIT

    @property
    def authenticator(self):
        return AnonexAuth(
            api_key=self.api_key,
            secret_key=self.secret_key,
            time_provider=self._time_synchronizer)

    @property
    def name(self) -> str:
        return "anonex"

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID_PREFIX

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def check_network_request_path(self):
        return CONSTANTS.PING_PATH_URL

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    async def get_all_pairs_prices(self) -> List[Dict[str, str]]:
        """
        Fetches ticker prices for all pairs.
        GET /api/v2/tickers
        Returns: [{"ticker_id": "BTC_USDT", "last_price": "50000", ...}, ...]
        """
        pairs_prices = await self._api_get(path_url=CONSTANTS.TICKER_PATH_URL)
        return pairs_prices

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        # AnonEx does not have timestamp-based request validation like Binance
        return False

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        return str(CONSTANTS.ORDER_NOT_EXIST_ERROR_CODE) in str(
            status_update_exception
        ) and CONSTANTS.ORDER_NOT_EXIST_MESSAGE in str(status_update_exception)

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        return str(CONSTANTS.ORDER_NOT_EXIST_ERROR_CODE) in str(
            cancelation_exception
        ) and CONSTANTS.ORDER_NOT_EXIST_MESSAGE in str(cancelation_exception)

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
            domain=self._domain,
            auth=self._auth)

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return AnonexAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
            api_factory=self._web_assistants_factory)

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return AnonexAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self.domain,
        )

    def _get_fee(self,
                 base_currency: str,
                 quote_currency: str,
                 order_type: OrderType,
                 order_side: TradeType,
                 amount: Decimal,
                 price: Decimal = s_decimal_NaN,
                 is_maker: Optional[bool] = None) -> TradeFeeBase:
        is_maker = order_type is OrderType.LIMIT_MAKER
        return DeductedFromReturnsTradeFee(percent=self.estimate_fee_pct(is_maker))

    async def _place_order(self,
                           order_id: str,
                           trading_pair: str,
                           amount: Decimal,
                           trade_type: TradeType,
                           order_type: OrderType,
                           price: Decimal,
                           **kwargs) -> Tuple[str, float]:
        """
        Places an order on AnonEx.
        POST /api/v2/createorder
        Body: { symbol, side, type, quantity, price, userProvidedId, strictValidate }
        Response: { id, userProvidedId, market: {id, symbol}, side, type, price, quantity, ... }
        """
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        side_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        type_str = AnonexExchange.anonex_order_type(order_type)
        amount_str = f"{amount:f}"

        api_params = {
            "symbol": symbol,
            "side": side_str,
            "type": type_str,
            "quantity": amount_str,
            "userProvidedId": order_id,
            "strictValidate": True,
        }

        if order_type is not OrderType.MARKET:
            price_str = f"{price:f}"
            api_params["price"] = price_str

        order_result = await self._api_post(
            path_url=CONSTANTS.CREATE_ORDER_PATH_URL,
            data=api_params,
            is_auth_required=True)

        if "error" in order_result:
            raise IOError(f"Error placing order: {order_result['error']}")

        o_id = str(order_result.get("id", order_id))
        transact_time = self._time_synchronizer.time()

        return o_id, transact_time

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        """
        Cancels an order on AnonEx.
        POST /api/v2/cancelorder
        Body: { id: orderId, type: "standard" }
        Response: { success: true, id: "..." }
        """
        # Use the exchange order ID if available, otherwise the client order ID (userProvidedId)
        cancel_id = tracked_order.exchange_order_id or order_id

        api_params = {
            "id": cancel_id,
            "type": "standard",
        }

        cancel_result = await self._api_post(
            path_url=CONSTANTS.CANCEL_ORDER_PATH_URL,
            data=api_params,
            is_auth_required=True)

        if cancel_result.get("success") is True:
            return True

        if "error" in cancel_result:
            raise IOError(f"Error cancelling order: {cancel_result['error']}")

        return False

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Parses market list from AnonEx into TradingRule objects.
        The exchange_info_dict comes from GET /api/v2/market/getlist which returns a list of markets.
        Each market has: symbol, priceDecimals, quantityDecimals, isActive, etc.

        We also fetch individual market info for min order sizes via GET /api/v2/market/info.
        """
        retval = []
        # exchange_info_dict is actually a list from /market/getlist
        markets = exchange_info_dict if isinstance(exchange_info_dict, list) else [exchange_info_dict]

        for market in markets:
            try:
                if not anonex_utils.is_exchange_information_valid(market):
                    continue

                symbol = market.get("symbol", "")
                if "/" not in symbol:
                    continue

                base, quote = symbol.split("/")
                trading_pair = combine_to_hb_trading_pair(base=base, quote=quote)

                price_decimals = market.get("priceDecimals", 8)
                quantity_decimals = market.get("quantityDecimals", 8)

                min_price_increment = Decimal(10) ** -Decimal(price_decimals)
                min_base_amount_increment = Decimal(10) ** -Decimal(quantity_decimals)

                # AnonEx doesn't expose min_order_size directly in the list endpoint.
                # Use a sensible default; actual validation happens server-side.
                min_order_size = min_base_amount_increment
                min_notional = Decimal("0")

                retval.append(
                    TradingRule(
                        trading_pair,
                        min_order_size=min_order_size,
                        min_price_increment=min_price_increment,
                        min_base_amount_increment=min_base_amount_increment,
                        min_notional_size=min_notional,
                    ))
            except Exception:
                self.logger().exception(f"Error parsing the trading pair rule {market}. Skipping.")

        return retval

    async def _update_trading_fees(self):
        """
        Fetches trading fees from AnonEx.
        GET /api/v2/tradingfees (authenticated)
        Response: { takerFee: "0.2", makerFee: "0.2" }
        """
        pass

    async def _user_stream_event_listener(self):
        """
        Processes user stream events from the AnonEx WebSocket.
        Events include balance updates from the subscribeBalances channel.

        Since AnonEx doesn't push individual order updates via WebSocket to API users,
        we rely on REST polling for order status updates (handled by the base class).
        Balance updates come as:
        {"jsonrpc": "2.0", "method": "currentBalances", "result": [{"ticker": "BTC", "available": "1.0", "held": "0.5"}, ...]}
        """
        async for event_message in self._iter_user_event_queue():
            try:
                method = event_message.get("method", "")

                if method in ("currentBalances", "balanceUpdate"):
                    balances = event_message.get("result", event_message.get("params", {}).get("data", []))
                    if isinstance(balances, list):
                        for balance_entry in balances:
                            asset_name = balance_entry.get("ticker", balance_entry.get("asset", ""))
                            if not asset_name:
                                continue
                            available = Decimal(str(balance_entry.get("available", "0")))
                            held = Decimal(str(balance_entry.get("held", "0")))
                            total = available + held
                            self._account_available_balances[asset_name] = available
                            self._account_balances[asset_name] = total

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await self._sleep(5.0)

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        """
        Fetches all trade fills for a specific order.
        GET /api/v2/getorderwithtrades/:orderId
        """
        trade_updates = []

        order_id = order.exchange_order_id or order.client_order_id
        if order_id is None:
            return trade_updates

        try:
            order_data = await self._api_get(
                path_url=f"{CONSTANTS.GET_ORDER_WITH_TRADES_PATH_URL}/{order_id}",
                is_auth_required=True,
                limit_id=CONSTANTS.GET_ORDER_WITH_TRADES_PATH_URL)

            if "error" in order_data:
                return trade_updates

            trades = order_data.get("trades", [])
            for trade in trades:
                fee_amount = Decimal(str(trade.get("fee", "0")))
                # Determine fee token: for buys it's the base asset, for sells it's the quote
                trading_pair = order.trading_pair
                base, quote = trading_pair.split("-")

                # Check for alternate fee asset (e.g., exchange token)
                fee_token = trade.get("alternateFeeAsset")
                if fee_token:
                    fee_amount = Decimal(str(trade.get("alternateFee", "0")))
                else:
                    fee_token = base if order.trade_type is TradeType.BUY else quote

                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=order.trade_type,
                    percent_token=fee_token,
                    flat_fees=[TokenAmount(amount=fee_amount, token=fee_token)]
                )

                fill_price = Decimal(str(trade["price"]))
                fill_amount = Decimal(str(trade["quantity"]))

                trade_update = TradeUpdate(
                    trade_id=str(trade["id"]),
                    client_order_id=order.client_order_id,
                    exchange_order_id=str(order_data.get("id", order_id)),
                    trading_pair=trading_pair,
                    fee=fee,
                    fill_base_amount=fill_amount,
                    fill_quote_amount=fill_amount * fill_price,
                    fill_price=fill_price,
                    fill_timestamp=self._parse_timestamp(trade.get("createdAt", 0)),
                )
                trade_updates.append(trade_update)

        except Exception:
            self.logger().exception(f"Error fetching trades for order {order_id}")

        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        """
        Fetches order status from AnonEx.
        GET /api/v2/getorder/:orderId
        Response: { id, userProvidedId, market, side, type, price, quantity, executedQuantity,
                    remainQuantity, status, isActive, createdAt, updatedAt }
        """
        order_id = tracked_order.exchange_order_id or tracked_order.client_order_id

        updated_order_data = await self._api_get(
            path_url=f"{CONSTANTS.GET_ORDER_PATH_URL}/{order_id}",
            is_auth_required=True)

        if "error" in updated_order_data:
            raise IOError(f"Error fetching order status: {updated_order_data['error']}")

        # Map AnonEx status to Hummingbot OrderState
        anonex_status = updated_order_data.get("status", "")
        is_active = updated_order_data.get("isActive", False)
        executed_qty = Decimal(str(updated_order_data.get("executedQuantity", "0")))
        total_qty = Decimal(str(updated_order_data.get("quantity", "0")))

        if is_active and executed_qty > 0:
            new_state = CONSTANTS.ORDER_STATE.get("Partially Filled", CONSTANTS.ORDER_STATE["Active"])
        elif is_active:
            new_state = CONSTANTS.ORDER_STATE.get("Active", CONSTANTS.ORDER_STATE["New"])
        elif not is_active and executed_qty >= total_qty and total_qty > 0:
            new_state = CONSTANTS.ORDER_STATE["Filled"]
        elif not is_active and anonex_status == "Cancelled":
            new_state = CONSTANTS.ORDER_STATE["Cancelled"]
        else:
            new_state = CONSTANTS.ORDER_STATE.get(anonex_status, CONSTANTS.ORDER_STATE.get("Active"))

        order_update = OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=str(updated_order_data.get("id", order_id)),
            trading_pair=tracked_order.trading_pair,
            update_timestamp=self._parse_timestamp(updated_order_data.get("updatedAt", 0)),
            new_state=new_state,
        )

        return order_update

    async def _update_balances(self):
        """
        Fetches all balances from AnonEx.
        GET /api/v2/balances
        Response: [{ asset: "BTC", name: "Bitcoin", available: "1.0", pending: "0", held: "0.5", assetid: "..." }, ...]
        """
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        account_info = await self._api_get(
            path_url=CONSTANTS.BALANCES_PATH_URL,
            is_auth_required=True)

        if isinstance(account_info, list):
            for balance_entry in account_info:
                asset_name = balance_entry.get("asset", "")
                if not asset_name:
                    continue
                available = Decimal(str(balance_entry.get("available", "0")))
                held = Decimal(str(balance_entry.get("held", "0")))
                total = available + held
                self._account_available_balances[asset_name] = available
                self._account_balances[asset_name] = total
                remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        """
        Initializes the trading pair symbol map from AnonEx market list.
        AnonEx uses "/" as separator (e.g., "BTC/USDT"), Hummingbot uses "-" (e.g., "BTC-USDT").
        The exchange symbol is the "/" form, the Hummingbot symbol is the "-" form.
        """
        mapping = bidict()
        markets = exchange_info if isinstance(exchange_info, list) else [exchange_info]
        for market_data in markets:
            if not anonex_utils.is_exchange_information_valid(market_data):
                continue
            symbol = market_data.get("symbol", "")
            if "/" not in symbol:
                continue
            base, quote = symbol.split("/")
            hb_pair = combine_to_hb_trading_pair(base=base, quote=quote)
            mapping[symbol] = hb_pair
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        """
        Fetches the last traded price for a trading pair.
        GET /api/v2/ticker/:symbol
        Response: { ticker_id, last_price, base_volume, ... }
        """
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        # AnonEx ticker endpoint uses _ separator in URL path
        ticker_symbol = symbol.replace("/", "_")

        resp_json = await self._api_request(
            method=RESTMethod.GET,
            path_url=f"{CONSTANTS.TICKER_SINGLE_PATH_URL}/{ticker_symbol}",
        )

        return float(resp_json.get("last_price", 0))

    @staticmethod
    def _parse_timestamp(timestamp_value) -> float:
        """Parse various timestamp formats from AnonEx responses."""
        if isinstance(timestamp_value, (int, float)):
            # If it's a large number, it's milliseconds
            if timestamp_value > 1e12:
                return timestamp_value / 1000.0
            return float(timestamp_value)
        if isinstance(timestamp_value, str):
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
                return dt.timestamp()
            except (ValueError, AttributeError):
                pass
        import time
        return time.time()
