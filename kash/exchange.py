"""Exchange interface using CCXT library."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal
import ccxt

from .config import TradingConfig
from .utils import logger


@dataclass
class Order:
    """Represents a trading order."""
    id: str
    symbol: str
    side: Literal["buy", "sell"]
    price: float
    amount: float
    status: Literal["open", "filled", "canceled", "partial"]
    filled: float = 0.0
    timestamp: str = ""
    
    @property
    def is_filled(self) -> bool:
        return self.status == "filled"
    
    @property
    def is_open(self) -> bool:
        return self.status == "open"


class ExchangeInterface(ABC):
    """Abstract interface for exchange operations."""
    
    @abstractmethod
    def get_ticker_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        pass
    
    @abstractmethod
    def place_limit_buy(self, symbol: str, amount: float, price: float) -> Order:
        """Place a limit buy order."""
        pass
    
    @abstractmethod
    def place_limit_sell(self, symbol: str, amount: float, price: float) -> Order:
        """Place a limit sell order."""
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str, symbol: str) -> Order:
        """Check status of an order."""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        pass
    
    @abstractmethod
    def get_balance(self, currency: str) -> float:
        """Get available balance for a currency."""
        pass
    
    @abstractmethod
    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol. Returns count canceled."""
        pass


class CCXTExchange(ExchangeInterface):
    """Live exchange implementation using CCXT."""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        exchange_class = getattr(ccxt, config.exchange_id)
        self.exchange = exchange_class({
            "apiKey": config.api_key,
            "secret": config.api_secret,
            "enableRateLimit": True,
        })
        logger.info(f"Connected to {config.exchange_id} exchange")
    
    def get_ticker_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        return ticker["last"]
    
    def place_limit_buy(self, symbol: str, amount: float, price: float) -> Order:
        result = self.exchange.create_limit_buy_order(symbol, amount, price)
        logger.info(f"BUY order placed: {amount} {symbol} @ {price}")
        return self._parse_order(result)
    
    def place_limit_sell(self, symbol: str, amount: float, price: float) -> Order:
        result = self.exchange.create_limit_sell_order(symbol, amount, price)
        logger.info(f"SELL order placed: {amount} {symbol} @ {price}")
        return self._parse_order(result)
    
    def get_order_status(self, order_id: str, symbol: str) -> Order:
        result = self.exchange.fetch_order(order_id, symbol)
        return self._parse_order(result)
    
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            self.exchange.cancel_order(order_id, symbol)
            logger.info(f"Order {order_id} canceled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def get_balance(self, currency: str) -> float:
        balance = self.exchange.fetch_balance()
        return balance.get(currency, {}).get("free", 0.0)
    
    def cancel_all_orders(self, symbol: str) -> int:
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            for order in orders:
                self.exchange.cancel_order(order["id"], symbol)
            logger.info(f"Canceled {len(orders)} orders for {symbol}")
            return len(orders)
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return 0
    
    def _parse_order(self, data: dict) -> Order:
        return Order(
            id=data["id"],
            symbol=data["symbol"],
            side=data["side"],
            price=data["price"],
            amount=data["amount"],
            status=data["status"],
            filled=data.get("filled", 0.0),
            timestamp=data.get("datetime", ""),
        )


def create_exchange(config: TradingConfig) -> ExchangeInterface:
    """Factory function to create appropriate exchange interface."""
    if config.trading_mode == "simulation":
        from .simulator import SimulatedExchange
        return SimulatedExchange(config)
    return CCXTExchange(config)
