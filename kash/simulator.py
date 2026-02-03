"""Paper trading simulation for testing strategies without real money."""

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import ccxt

from .config import TradingConfig
from .exchange import ExchangeInterface, Order
from .utils import logger, format_price, format_percent


@dataclass
class SimulationState:
    """Tracks simulation portfolio and performance."""
    
    initial_investment: float = 1000.0
    quote_balance: float = 1000.0
    base_balance: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    total_profit: float = 0.0
    start_time: str = ""
    orders: dict = field(default_factory=dict)
    trade_history: list = field(default_factory=list)
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    @property
    def roi_percent(self) -> float:
        return ((self.total_profit) / self.initial_investment) * 100
    
    def to_dict(self) -> dict:
        return {
            "initial_investment": self.initial_investment,
            "quote_balance": self.quote_balance,
            "base_balance": self.base_balance,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "total_profit": self.total_profit,
            "start_time": self.start_time,
            "orders": self.orders,
            "trade_history": self.trade_history[-100:],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SimulationState":
        return cls(
            initial_investment=data.get("initial_investment", 1000.0),
            quote_balance=data.get("quote_balance", 1000.0),
            base_balance=data.get("base_balance", 0.0),
            total_trades=data.get("total_trades", 0),
            winning_trades=data.get("winning_trades", 0),
            total_profit=data.get("total_profit", 0.0),
            start_time=data.get("start_time", ""),
            orders=data.get("orders", {}),
            trade_history=data.get("trade_history", []),
        )


class SimulatedExchange(ExchangeInterface):
    """Simulated exchange for paper trading using real market prices."""
    
    STATE_FILE = Path("simulation_state.json")
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.exchange = ccxt.binance({"enableRateLimit": True})
        self.state = self._load_state()
        
        if not self.state.start_time:
            self.state.start_time = datetime.now().isoformat()
            self.state.initial_investment = config.investment
            self.state.quote_balance = config.investment
        
        logger.info("=" * 50)
        logger.info("SIMULATION MODE - No real trades will be executed")
        logger.info(f"Starting balance: {format_price(self.state.quote_balance)}")
        logger.info("=" * 50)
    
    def _load_state(self) -> SimulationState:
        """Load simulation state from file if exists."""
        if self.STATE_FILE.exists():
            try:
                data = json.loads(self.STATE_FILE.read_text())
                logger.info("Loaded existing simulation state")
                return SimulationState.from_dict(data)
            except Exception as e:
                logger.warning(f"Could not load state: {e}, starting fresh")
        return SimulationState()
    
    def _save_state(self):
        """Persist simulation state to file."""
        self.STATE_FILE.write_text(json.dumps(self.state.to_dict(), indent=2))
    
    def get_ticker_price(self, symbol: str, retries: int = 3) -> float:
        """Get real market price from exchange with retry logic."""
        ticker = self._fetch_ticker(symbol, retries)
        return ticker["last"]
    
    def _fetch_ticker(self, symbol: str, retries: int = 3) -> dict:
        """Fetch full ticker data with retry logic."""
        last_error = None
        for attempt in range(retries):
            try:
                logger.debug(f"API CALL: fetch_ticker({symbol}) attempt {attempt + 1}/{retries}")
                ticker = self.exchange.fetch_ticker(symbol)
                logger.debug(f"API RESPONSE: {symbol} price={ticker['last']} low={ticker.get('low')} high={ticker.get('high')}")
                return ticker
            except Exception as e:
                last_error = e
                logger.debug(f"API ERROR: {e} (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    wait_time = 2 ** attempt
                    logger.debug(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        raise last_error
    
    def place_limit_buy(self, symbol: str, amount: float, price: float) -> Order:
        """Simulate placing a buy order."""
        cost = amount * price
        logger.debug(f"PLACE BUY: {amount:.8f} {symbol} @ {format_price(price)} (cost: {format_price(cost)})")
        logger.debug(f"  Available balance: {format_price(self.state.quote_balance)}")
        
        if cost > self.state.quote_balance:
            logger.warning(f"Insufficient balance for buy: need {format_price(cost)}, have {format_price(self.state.quote_balance)}")
            raise ValueError("Insufficient balance")
        
        order_id = f"sim_buy_{uuid.uuid4().hex[:8]}"
        logger.debug(f"  Created order ID: {order_id}")
        order = Order(
            id=order_id,
            symbol=symbol,
            side="buy",
            price=price,
            amount=amount,
            status="open",
            timestamp=datetime.now().isoformat(),
        )
        
        self.state.orders[order_id] = {
            "order": order.__dict__,
            "reserved_quote": cost,
        }
        self.state.quote_balance -= cost
        self._save_state()
        
        logger.info(f"[SIM] BUY order: {amount:.6f} @ {format_price(price)} (reserved {format_price(cost)})")
        return order
    
    def place_limit_sell(self, symbol: str, amount: float, price: float) -> Order:
        """Simulate placing a sell order."""
        logger.debug(f"PLACE SELL: {amount:.8f} {symbol} @ {format_price(price)}")
        logger.debug(f"  Available base balance: {self.state.base_balance:.8f}")
        
        if amount > self.state.base_balance:
            logger.warning(f"Insufficient {self.config.base_currency} for sell: need {amount:.6f}, have {self.state.base_balance:.6f}")
            raise ValueError("Insufficient balance")
        
        order_id = f"sim_sell_{uuid.uuid4().hex[:8]}"
        logger.debug(f"  Created order ID: {order_id}")
        order = Order(
            id=order_id,
            symbol=symbol,
            side="sell",
            price=price,
            amount=amount,
            status="open",
            timestamp=datetime.now().isoformat(),
        )
        
        self.state.orders[order_id] = {
            "order": order.__dict__,
            "reserved_base": amount,
        }
        self.state.base_balance -= amount
        self._save_state()
        
        logger.info(f"[SIM] SELL order: {amount:.6f} @ {format_price(price)}")
        return order
    
    def get_order_status(self, order_id: str, symbol: str) -> Order:
        """Check if simulated order would have filled based on price range (high/low)."""
        logger.debug(f"CHECK ORDER: {order_id}")
        
        if order_id not in self.state.orders:
            logger.debug(f"  Order not found!")
            raise ValueError(f"Order {order_id} not found")
        
        order_data = self.state.orders[order_id]
        order = Order(**order_data["order"])
        logger.debug(f"  Order: {order.side} {order.amount:.8f} @ {format_price(order.price)} (status: {order.status})")
        
        if order.status != "open":
            logger.debug(f"  Order already {order.status}, skipping")
            return order
        
        try:
            ticker = self._fetch_ticker(symbol)
            current_price = ticker["last"]
        except Exception as e:
            logger.debug(f"  Failed to get price, skipping check: {e}")
            return order
        
        logger.debug(f"  Current price: {format_price(current_price)}, Order price: {format_price(order.price)}")
        
        # For buy orders: fill if current price dropped to or below order price
        if order.side == "buy" and current_price <= order.price:
            logger.debug(f"  BUY condition met: current {format_price(current_price)} <= order {format_price(order.price)}")
            self._fill_buy_order(order_id, order, order_data)
        # For sell orders: fill if current price rose to or above order price
        elif order.side == "sell" and current_price >= order.price:
            logger.debug(f"  SELL condition met: current {format_price(current_price)} >= order {format_price(order.price)}")
            self._fill_sell_order(order_id, order, order_data)
        else:
            logger.debug(f"  No fill condition met")
        
        return Order(**self.state.orders[order_id]["order"])
    
    def _fill_buy_order(self, order_id: str, order: Order, order_data: dict):
        """Execute a buy order fill."""
        self.state.base_balance += order.amount
        
        order.status = "filled"
        order.filled = order.amount
        order_data["order"] = order.__dict__
        
        self.state.trade_history.append({
            "type": "buy",
            "price": order.price,
            "amount": order.amount,
            "timestamp": datetime.now().isoformat(),
        })
        
        self._save_state()
        logger.info(f"[SIM] BUY FILLED: {order.amount:.6f} @ {format_price(order.price)}")
    
    def _fill_sell_order(self, order_id: str, order: Order, order_data: dict):
        """Execute a sell order fill."""
        proceeds = order.amount * order.price
        self.state.quote_balance += proceeds
        
        last_buy = next(
            (t for t in reversed(self.state.trade_history) if t["type"] == "buy"),
            None
        )
        
        profit = 0.0
        if last_buy:
            cost = order.amount * last_buy["price"]
            profit = proceeds - cost
            self.state.total_profit += profit
            self.state.total_trades += 1
            if profit > 0:
                self.state.winning_trades += 1
        
        order.status = "filled"
        order.filled = order.amount
        order_data["order"] = order.__dict__
        
        self.state.trade_history.append({
            "type": "sell",
            "price": order.price,
            "amount": order.amount,
            "profit": profit,
            "timestamp": datetime.now().isoformat(),
        })
        
        self._save_state()
        profit_str = format_price(profit) if profit >= 0 else f"-{format_price(abs(profit))}"
        logger.info(f"[SIM] SELL FILLED: {order.amount:.6f} @ {format_price(order.price)} (profit: {profit_str})")
    
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a simulated order and return reserved funds."""
        if order_id not in self.state.orders:
            return False
        
        order_data = self.state.orders[order_id]
        order = Order(**order_data["order"])
        
        if order.status != "open":
            return False
        
        if order.side == "buy":
            self.state.quote_balance += order_data.get("reserved_quote", 0)
        else:
            self.state.base_balance += order_data.get("reserved_base", 0)
        
        order.status = "canceled"
        order_data["order"] = order.__dict__
        self._save_state()
        
        logger.info(f"[SIM] Order {order_id} canceled")
        return True
    
    def get_balance(self, currency: str) -> float:
        """Get simulated balance."""
        if currency == self.config.quote_currency:
            return self.state.quote_balance
        elif currency == self.config.base_currency:
            return self.state.base_balance
        return 0.0
    
    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open simulated orders."""
        canceled = 0
        for order_id in list(self.state.orders.keys()):
            if self.cancel_order(order_id, symbol):
                canceled += 1
        return canceled
    
    def get_portfolio_value(self, current_price: float) -> float:
        """Calculate total portfolio value in quote currency."""
        base_value = self.state.base_balance * current_price
        
        reserved_quote = sum(
            d.get("reserved_quote", 0) 
            for d in self.state.orders.values() 
            if Order(**d["order"]).status == "open"
        )
        reserved_base_value = sum(
            d.get("reserved_base", 0) * current_price
            for d in self.state.orders.values()
            if Order(**d["order"]).status == "open"
        )
        
        return self.state.quote_balance + base_value + reserved_quote + reserved_base_value
    
    def print_summary(self):
        """Print simulation performance summary."""
        current_price = self.get_ticker_price(self.config.trading_pair)
        portfolio_value = self.get_portfolio_value(current_price)
        unrealized_pnl = portfolio_value - self.state.initial_investment
        
        logger.info("")
        logger.info("=" * 50)
        logger.info("SIMULATION SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Started: {self.state.start_time}")
        logger.info(f"Initial Investment: {format_price(self.state.initial_investment)}")
        logger.info(f"Current Portfolio: {format_price(portfolio_value)}")
        logger.info(f"Unrealized P&L: {format_price(unrealized_pnl)} ({format_percent(unrealized_pnl/self.state.initial_investment*100)})")
        logger.info(f"Realized Profit: {format_price(self.state.total_profit)}")
        logger.info(f"Total Trades: {self.state.total_trades}")
        logger.info(f"Win Rate: {self.state.win_rate:.1f}%")
        logger.info(f"Quote Balance: {format_price(self.state.quote_balance)}")
        logger.info(f"Base Balance: {self.state.base_balance:.6f} {self.config.base_currency}")
        logger.info("=" * 50)
