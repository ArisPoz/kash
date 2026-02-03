"""Web UI for monitoring the trading bot."""

import threading
from flask import Flask, render_template_string, jsonify

from .exchange import Order
from .utils import logger

app = Flask(__name__)

_bot_instance = None


def set_bot_instance(bot):
    """Set the bot instance for the web UI to access."""
    global _bot_instance
    _bot_instance = bot


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kash Trading Bot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        @keyframes pulse-green { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @keyframes pulse-red { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .pulse-green { animation: pulse-green 2s infinite; }
        .pulse-red { animation: pulse-red 2s infinite; }
        .grid-line { transition: all 0.3s ease; }
        .grid-line:hover { transform: scale(1.02); }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="container mx-auto px-4 py-8 max-w-6xl">
        <!-- Header -->
        <div class="flex items-center justify-between mb-8">
            <div>
                <h1 class="text-3xl font-bold text-white flex items-center gap-3">
                    <span class="text-4xl">💰</span> Kash Trading Bot
                </h1>
                <p class="text-gray-400 mt-1">Grid Trading Strategy</p>
            </div>
            <div id="status-badge" class="flex items-center gap-2 px-4 py-2 rounded-full bg-gray-800">
                <span class="w-3 h-3 rounded-full bg-green-500 pulse-green"></span>
                <span class="text-sm">Running</span>
            </div>
        </div>

        <!-- Price Card -->
        <div class="bg-gray-800 rounded-2xl p-6 mb-6 border border-gray-700">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-gray-400 text-sm uppercase tracking-wide">Current Price</p>
                    <p id="current-price" class="text-4xl font-bold text-white mt-1">€--,---.--</p>
                    <p id="trading-pair" class="text-gray-500 mt-1">BTC/EUR</p>
                </div>
                <div class="text-right">
                    <p class="text-gray-400 text-sm uppercase tracking-wide">Grid Range</p>
                    <p class="text-lg text-gray-300 mt-1">
                        <span id="lower-limit" class="text-red-400">€--,---</span>
                        <span class="text-gray-500 mx-2">→</span>
                        <span id="upper-limit" class="text-green-400">€--,---</span>
                    </p>
                </div>
            </div>
        </div>

        <!-- Stats Grid -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <p class="text-gray-400 text-xs uppercase">Portfolio Value</p>
                <p id="portfolio-value" class="text-2xl font-bold text-white mt-1">€---.--</p>
            </div>
            <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <p class="text-gray-400 text-xs uppercase">Realized Profit</p>
                <p id="realized-profit" class="text-2xl font-bold text-green-400 mt-1">€-.--</p>
            </div>
            <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <p class="text-gray-400 text-xs uppercase">Total Trades</p>
                <p id="total-trades" class="text-2xl font-bold text-white mt-1">-</p>
            </div>
            <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <p class="text-gray-400 text-xs uppercase">Win Rate</p>
                <p id="win-rate" class="text-2xl font-bold text-white mt-1">--%</p>
            </div>
        </div>

        <!-- Orders Section -->
        <div class="grid md:grid-cols-2 gap-6">
            <!-- Buy Orders -->
            <div class="bg-gray-800 rounded-2xl p-6 border border-gray-700">
                <div class="flex items-center gap-2 mb-4">
                    <span class="w-3 h-3 rounded-full bg-green-500"></span>
                    <h2 class="text-lg font-semibold">Buy Orders</h2>
                    <span id="buy-count" class="ml-auto bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full text-sm">0</span>
                </div>
                <div id="buy-orders" class="space-y-2 max-h-80 overflow-y-auto">
                    <p class="text-gray-500 text-center py-4">Loading...</p>
                </div>
            </div>

            <!-- Sell Orders -->
            <div class="bg-gray-800 rounded-2xl p-6 border border-gray-700">
                <div class="flex items-center gap-2 mb-4">
                    <span class="w-3 h-3 rounded-full bg-red-500"></span>
                    <h2 class="text-lg font-semibold">Sell Orders</h2>
                    <span id="sell-count" class="ml-auto bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full text-sm">0</span>
                </div>
                <div id="sell-orders" class="space-y-2 max-h-80 overflow-y-auto">
                    <p class="text-gray-500 text-center py-4">Loading...</p>
                </div>
            </div>
        </div>

        <!-- Balances -->
        <div class="mt-6 bg-gray-800 rounded-2xl p-6 border border-gray-700">
            <h2 class="text-lg font-semibold mb-4">Balances</h2>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <p class="text-gray-400 text-sm">Quote Currency (EUR)</p>
                    <p id="quote-balance" class="text-xl font-mono text-white">€---.--</p>
                </div>
                <div>
                    <p class="text-gray-400 text-sm">Base Currency (BTC)</p>
                    <p id="base-balance" class="text-xl font-mono text-white">-.-------- BTC</p>
                </div>
            </div>
        </div>

        <!-- Trade History -->
        <div class="mt-6 bg-gray-800 rounded-2xl p-6 border border-gray-700">
            <div class="flex items-center gap-2 mb-4">
                <span class="text-xl">📜</span>
                <h2 class="text-lg font-semibold">Trade History</h2>
                <span id="history-count" class="ml-auto bg-gray-600/50 text-gray-300 px-2 py-0.5 rounded-full text-sm">0</span>
            </div>
            <div id="trade-history" class="space-y-2 max-h-96 overflow-y-auto">
                <p class="text-gray-500 text-center py-4">No trades yet</p>
            </div>
        </div>

        <!-- Footer -->
        <div class="mt-8 text-center text-gray-500 text-sm">
            <p>Last updated: <span id="last-update">--:--:--</span></p>
            <p class="mt-1">Mode: <span id="trading-mode" class="text-yellow-400">SIMULATION</span></p>
        </div>
    </div>

    <script>
        function formatPrice(price) {
            return '€' + price.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        function renderOrder(order, side) {
            const bgColor = side === 'buy' ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30';
            const textColor = side === 'buy' ? 'text-green-400' : 'text-red-400';
            return `
                <div class="grid-line ${bgColor} border rounded-lg p-3 flex justify-between items-center">
                    <div>
                        <span class="font-mono ${textColor}">${formatPrice(order.price)}</span>
                    </div>
                    <div class="text-right">
                        <span class="text-gray-400 text-sm">${order.amount.toFixed(8)}</span>
                    </div>
                </div>
            `;
        }

        function renderTrade(trade) {
            const isBuy = trade.type === 'buy';
            const bgColor = isBuy ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30';
            const textColor = isBuy ? 'text-green-400' : 'text-red-400';
            const icon = isBuy ? '📥' : '📤';
            const profitHtml = trade.profit !== undefined && trade.profit !== null
                ? `<span class="${trade.profit >= 0 ? 'text-green-400' : 'text-red-400'} text-sm ml-2">${trade.profit >= 0 ? '+' : ''}${formatPrice(trade.profit)}</span>`
                : '';
            const timeStr = trade.timestamp ? new Date(trade.timestamp).toLocaleString() : '';
            return `
                <div class="grid-line ${bgColor} border rounded-lg p-3">
                    <div class="flex justify-between items-center">
                        <div class="flex items-center gap-2">
                            <span>${icon}</span>
                            <span class="font-semibold ${textColor}">${trade.type.toUpperCase()}</span>
                            <span class="font-mono ${textColor}">${formatPrice(trade.price)}</span>
                            ${profitHtml}
                        </div>
                        <div class="text-right">
                            <span class="text-gray-400 text-sm">${trade.amount.toFixed(8)}</span>
                        </div>
                    </div>
                    ${timeStr ? `<div class="text-gray-500 text-xs mt-1">${timeStr}</div>` : ''}
                </div>
            `;
        }

        async function fetchData() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();

                // Update price
                document.getElementById('current-price').textContent = formatPrice(data.current_price);
                document.getElementById('trading-pair').textContent = data.trading_pair;
                document.getElementById('lower-limit').textContent = formatPrice(data.lower_limit);
                document.getElementById('upper-limit').textContent = formatPrice(data.upper_limit);

                // Update stats
                document.getElementById('portfolio-value').textContent = formatPrice(data.portfolio_value);
                document.getElementById('realized-profit').textContent = formatPrice(data.realized_profit);
                document.getElementById('total-trades').textContent = data.total_trades;
                document.getElementById('win-rate').textContent = data.win_rate.toFixed(1) + '%';

                // Update balances
                document.getElementById('quote-balance').textContent = formatPrice(data.quote_balance);
                document.getElementById('base-balance').textContent = data.base_balance.toFixed(8) + ' ' + data.base_currency;

                // Update orders
                const buyOrders = data.orders.filter(o => o.side === 'buy').sort((a, b) => b.price - a.price);
                const sellOrders = data.orders.filter(o => o.side === 'sell').sort((a, b) => a.price - b.price);

                document.getElementById('buy-count').textContent = buyOrders.length;
                document.getElementById('sell-count').textContent = sellOrders.length;

                document.getElementById('buy-orders').innerHTML = buyOrders.length 
                    ? buyOrders.map(o => renderOrder(o, 'buy')).join('')
                    : '<p class="text-gray-500 text-center py-4">No buy orders</p>';

                document.getElementById('sell-orders').innerHTML = sellOrders.length
                    ? sellOrders.map(o => renderOrder(o, 'sell')).join('')
                    : '<p class="text-gray-500 text-center py-4">No sell orders</p>';

                // Update trade history
                const trades = data.trade_history || [];
                document.getElementById('history-count').textContent = trades.length;
                document.getElementById('trade-history').innerHTML = trades.length
                    ? trades.slice().reverse().map(t => renderTrade(t)).join('')
                    : '<p class="text-gray-500 text-center py-4">No trades yet</p>';

                // Update timestamp
                document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
                document.getElementById('trading-mode').textContent = data.trading_mode.toUpperCase();

                // Update status badge
                const badge = document.getElementById('status-badge');
                if (data.is_running) {
                    badge.innerHTML = '<span class="w-3 h-3 rounded-full bg-green-500 pulse-green"></span><span class="text-sm">Running</span>';
                } else {
                    badge.innerHTML = '<span class="w-3 h-3 rounded-full bg-red-500"></span><span class="text-sm">Stopped</span>';
                }

            } catch (error) {
                console.error('Failed to fetch data:', error);
            }
        }

        // Initial fetch
        fetchData();
        // Refresh every 5 seconds
        setInterval(fetchData, 5000);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/status')
def api_status():
    if _bot_instance is None:
        return jsonify({"error": "Bot not initialized"}), 503
    
    try:
        exchange = _bot_instance.exchange
        strategy = _bot_instance.strategy
        config = _bot_instance.config
        
        current_price = exchange.get_ticker_price(config.trading_pair)
        
        # Get orders from strategy state
        orders = []
        for level in strategy.state.get_active_orders():
            orders.append({
                "id": level.order_id,
                "side": level.side,
                "price": level.price,
                "amount": level.amount,
                "status": level.status,
            })
        
        # Get simulation state if available
        portfolio_value = config.investment
        realized_profit = 0.0
        total_trades = 0
        win_rate = 0.0
        quote_balance = config.investment
        base_balance = 0.0
        
        if hasattr(exchange, 'state'):
            state = exchange.state
            portfolio_value = exchange.get_portfolio_value(current_price)
            realized_profit = state.total_profit
            total_trades = state.total_trades
            win_rate = state.win_rate
            quote_balance = state.quote_balance
            base_balance = state.base_balance
        
        return jsonify({
            "trading_pair": config.trading_pair,
            "base_currency": config.base_currency,
            "current_price": current_price,
            "lower_limit": strategy.state.lower_limit,
            "upper_limit": strategy.state.upper_limit,
            "portfolio_value": portfolio_value,
            "realized_profit": realized_profit,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "quote_balance": quote_balance,
            "base_balance": base_balance,
            "orders": orders,
            "is_running": strategy.is_running,
            "trading_mode": config.trading_mode,
            "trade_history": state.trade_history if hasattr(exchange, 'state') else [],
        })
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500


def run_web_ui(host: str = "127.0.0.1", port: int = 5000):
    """Run the web UI in a separate thread."""
    import logging
    # Suppress Flask's default logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    
    def run():
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"Web UI started at http://127.0.0.1:{port}")
    return thread
