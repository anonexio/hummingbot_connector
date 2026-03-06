from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

DEFAULT_DOMAIN = ""

HBOT_ORDER_ID_PREFIX = "hbot-"
MAX_ORDER_ID_LEN = 36

# Base URLs
REST_URL = "https://api.anonex.io/api/v2"
WSS_URL = "wss://ws.anonex.io"

# Public API endpoints
EXCHANGE_INFO_PATH_URL = "/market/getlist"
MARKET_INFO_PATH_URL = "/market/info"
TICKER_PATH_URL = "/tickers"
TICKER_SINGLE_PATH_URL = "/ticker"
ORDERBOOK_PATH_URL = "/market/orderbook"
TRADES_PATH_URL = "/market/trades"
SERVER_TIME_PATH_URL = "/time"
PING_PATH_URL = "/time"

# Private API endpoints
BALANCES_PATH_URL = "/balances"
CREATE_ORDER_PATH_URL = "/createorder"
CANCEL_ORDER_PATH_URL = "/cancelorder"
CANCEL_ALL_ORDERS_PATH_URL = "/cancelallorders"
GET_ORDER_PATH_URL = "/getorder"
GET_ORDER_WITH_TRADES_PATH_URL = "/getorderwithtrades"
GET_ORDERS_PATH_URL = "/getorders"
TRADING_FEES_PATH_URL = "/tradingfees"

# Order sides
SIDE_BUY = "buy"
SIDE_SELL = "sell"

# Order types
ORDER_TYPE_LIMIT = "limit"
ORDER_TYPE_MARKET = "market"

# WebSocket methods (JSON-RPC style)
WS_METHOD_PING = "ping"
WS_METHOD_LOGIN = "login"
WS_METHOD_SUBSCRIBE_TICKER = "subscribeTicker"
WS_METHOD_SUBSCRIBE_ORDERBOOK = "subscribeOrderbook"
WS_METHOD_SUBSCRIBE_TRADES = "subscribeTrades"
WS_METHOD_UNSUBSCRIBE_ORDERBOOK = "unsubscribeOrderbook"
WS_METHOD_UNSUBSCRIBE_TRADES = "unsubscribeTrades"
WS_METHOD_SUBSCRIBE_BALANCES = "subscribeBalances"
WS_METHOD_GET_TRADING_BALANCE = "getTradingBalance"

WS_HEARTBEAT_TIME_INTERVAL = 30

# Order States mapping from AnonEx status to Hummingbot OrderState
ORDER_STATE = {
    "New": OrderState.OPEN,
    "Active": OrderState.OPEN,
    "Partially Filled": OrderState.PARTIALLY_FILLED,
    "Filled": OrderState.FILLED,
    "Cancelled": OrderState.CANCELED,
    "Expired": OrderState.FAILED,
}

# Rate Limit IDs
REQUEST_WEIGHT = "REQUEST_WEIGHT"
ORDERS_LIMIT = "ORDERS_LIMIT"

ONE_MINUTE = 60
ONE_SECOND = 1

MAX_REQUEST = 300

# Rate Limits
RATE_LIMITS = [
    RateLimit(limit_id=REQUEST_WEIGHT, limit=MAX_REQUEST, time_interval=ONE_MINUTE),
    RateLimit(limit_id=ORDERS_LIMIT, limit=30, time_interval=ONE_SECOND),
    # Public endpoints
    RateLimit(limit_id=EXCHANGE_INFO_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=MARKET_INFO_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 1)]),
    RateLimit(limit_id=TICKER_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 2)]),
    RateLimit(limit_id=ORDERBOOK_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=TRADES_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 2)]),
    RateLimit(limit_id=SERVER_TIME_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 1)]),
    RateLimit(limit_id=PING_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 1)]),
    # Private endpoints
    RateLimit(limit_id=BALANCES_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=CREATE_ORDER_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 2),
                             LinkedLimitWeightPair(ORDERS_LIMIT, 1)]),
    RateLimit(limit_id=CANCEL_ORDER_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 2),
                             LinkedLimitWeightPair(ORDERS_LIMIT, 1)]),
    RateLimit(limit_id=GET_ORDER_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 2)]),
    RateLimit(limit_id=GET_ORDER_WITH_TRADES_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=GET_ORDERS_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 5)]),
    RateLimit(limit_id=TRADING_FEES_PATH_URL, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 2)]),
]

ORDER_NOT_EXIST_ERROR_CODE = 20002
ORDER_NOT_EXIST_MESSAGE = "Not Found"
