# AnonEx Hummingbot Connector

An exchange connector for [Hummingbot](https://github.com/hummingbot/hummingbot) that enables automated trading on [AnonEx](https://anonex.io).

## Prerequisites

- A working [Hummingbot installation](https://hummingbot.org/installation/) (source install recommended)
- An AnonEx account with API keys generated (Settings > API Keys)
- API key must have `read,trade` permissions at minimum

## Installation

### 1. Clone this repository

```bash
git clone https://github.com/anonexio/hummingbot_connector.git
```

### 2. Copy the connector into your Hummingbot installation

```bash
cp -r hummingbot_connector/anonex /path/to/hummingbot/hummingbot/connector/exchange/anonex
```

Replace `/path/to/hummingbot` with the actual path to your Hummingbot checkout.

### 3. Register the connector

Add the following entry to the connector settings. Open `hummingbot/client/settings.py` and add `"anonex"` to the `CONNECTOR_SETTINGS` dictionary:

```python
CONNECTOR_SETTINGS = {
    # ... existing connectors ...
    "anonex": ConnectorSetting(
        name="anonex",
        type=ConnectorType.Exchange,
        centralised=True,
        example_pair="BTC-USDT",
        use_ethereum_wallet=False,
        fee_type="Percent",
        fee_token="",
        default_fees=[0.2, 0.2],
    ),
}
```

### 4. Rebuild Hummingbot (source installs only)

If you installed Hummingbot from source, rebuild to pick up the new connector:

```bash
cd /path/to/hummingbot
./compile
```

If you are running Hummingbot via Docker, you will need to rebuild the Docker image.

## Configuration

### Connect your API keys

From the Hummingbot CLI:

```
connect anonex
```

You will be prompted for:
- **AnonEx API Key** - Your API key from AnonEx
- **AnonEx API Secret** - Your API secret from AnonEx

### Example: Running a market-making strategy

```
create
```

Then select:
- **Strategy**: `pure_market_making`
- **Exchange**: `anonex`
- **Trading pair**: `BTC-USDT` (use `-` separator, not `/`)

## Trading Pair Format

AnonEx uses `/` as the separator (e.g., `BTC/USDT`), but Hummingbot uses `-` (e.g., `BTC-USDT`). The connector handles this conversion automatically. Always use the `-` format when configuring strategies in Hummingbot.

## Supported Features

| Feature | Supported |
|---------|-----------|
| Limit orders | Yes |
| Market orders | Yes |
| Order cancellation | Yes |
| Batch cancel | Yes |
| Balance tracking | Yes (REST + WebSocket) |
| Order book streaming | Yes (WebSocket) |
| Trade streaming | Yes (WebSocket) |
| Order status polling | Yes (REST) |

## Authentication

The connector supports AnonEx's HMAC-SHA256 API authentication:

- **REST API**: Uses `x-api-key`, `x-api-nonce`, and `x-api-sign` headers
- **WebSocket**: Authenticates via the `login` JSON-RPC method with HMAC-SHA256 signed nonce

## File Structure

```
anonex/
  __init__.py                          # Package init
  anonex_constants.py                  # API URLs, endpoints, rate limits
  anonex_auth.py                       # HMAC-SHA256 authentication
  anonex_web_utils.py                  # URL builders, API factory
  anonex_utils.py                      # Config map, fee schema
  anonex_order_book.py                 # Order book message parsing
  anonex_api_order_book_data_source.py # REST + WebSocket order book data
  anonex_api_user_stream_data_source.py# WebSocket user data (balances)
  anonex_exchange.py                   # Main connector (orders, balances, rules)
  dummy.pxd                            # Cython stub (required by build)
  dummy.pyx                            # Cython stub (required by build)
```

## Troubleshooting

- **"Not Authorized" errors**: Verify your API key has `read,trade` permissions and is not IP-restricted (or your IP is whitelisted).
- **Trading pair not found**: Make sure the pair exists on AnonEx and use `-` format (e.g., `BTC-USDT`, not `BTC/USDT`).
- **Connection issues**: Check that your firewall allows outbound connections to `api.anonex.io` and `ws.anonex.io`.

## Links

- [AnonEx Exchange](https://anonex.io)
- [AnonEx API Documentation](https://anonex.io/api-docs)
- [Hummingbot Documentation](https://hummingbot.org/docs/)
- [Hummingbot Connector Developer Guide](https://hummingbot.org/developers/connectors/)

## License

MIT
