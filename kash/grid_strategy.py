"""Grid Trading Strategy - The Volatility Harvester.

This strategy profits from price oscillation without predicting direction:
1. Define a price range (e.g., ±10% of current price)
2. Divide range into grid levels
3. Place buy orders below current price, sell orders above
4. When buy fills → place sell at higher level
5. When sell fills → place buy at lower level
6. Repeat 24/7, harvesting small profits from market noise
"""

from dataclasses import dataclass, field
from typing import Literal

from .config import TradingConfig
from .exchange import ExchangeInterface, Order
from .risk_manager import RiskManager, RiskLevel
from .utils import logger, format_price


@dataclass
class GridLevel:
    """Represents a single grid level with its order."""
    price: float
    side: Literal["buy", "sell"]
    order_id: str | None = None
    status: Literal["pending", "active", "filled"] = "pending"
    amount: float = 0.0


@dataclass
class GridState:
    """Tracks the state of all grid levels."""
    levels: list[GridLevel] = field(default_factory=list)
    initial_price: float = 0.0
    upper_limit: float = 0.0
    lower_limit: float = 0.0
    
    def get_active_orders(self) -> list[GridLevel]:
        return [l for l in self.levels if l.status == "active"]
    
    def get_buy_levels(self) -> list[GridLevel]:
        return [l for l in self.levels if l.side == "buy"]
    
    def get_sell_levels(self) -> list[GridLevel]:
        return [l for l in self.levels if l.side == "sell"]


class GridStrategy:
    """
    Spot Grid Trading Strategy.
    
    Harvests profits from price volatility by maintaining a grid of
    buy and sell orders across a defined price range.
    """
    
    def __init__(
        self,
        config: TradingConfig,
        exchange: ExchangeInterface,
        risk_manager: RiskManager,
    ):
        self.config = config
        self.exchange = exchange
        self.risk_manager = risk_manager
        self.state = GridState()
        self.is_running = False
        self.panic_triggered = False
    
    def initialize(self) -> bool:
        """
        Initialize the grid with current market price.
        
        Returns True if initialization successful.
        """
        logger.debug("GRID INIT: Starting initialization...")
        try:
            current_price = self.exchange.get_ticker_price(self.config.trading_pair)
            logger.info(f"Current {self.config.trading_pair} price: {format_price(current_price)}")
            
            logger.debug("GRID INIT: Initializing risk manager...")
            self.risk_manager.initialize(current_price)
            
            logger.debug("GRID INIT: Setting up grid levels...")
            self._setup_grid(current_price)
            
            logger.debug("GRID INIT: Placing initial orders...")
            self._place_initial_orders(current_price)
            
            self.is_running = True
            logger.debug("GRID INIT: Complete!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize grid: {e}")
            return False
    
    def _setup_grid(self, current_price: float):
        """Calculate and create grid levels."""
        self.state.initial_price = current_price
        self.state.upper_limit = current_price * (1 + self.config.grid_range_percent / 100)
        self.state.lower_limit = current_price * (1 - self.config.grid_range_percent / 100)
        
        grid_step = (self.state.upper_limit - self.state.lower_limit) / self.config.grid_count
        
        order_value = self.config.order_size
        
        self.state.levels = []
        
        for i in range(self.config.grid_count + 1):
            level_price = self.state.lower_limit + (i * grid_step)
            amount = order_value / level_price
            
            if level_price < current_price:
                side = "buy"
            elif level_price > current_price:
                side = "sell"
            else:
                continue
            
            self.state.levels.append(GridLevel(
                price=level_price,
                side=side,
                amount=amount,
            ))
            logger.debug(f"  Grid level {i}: {side.upper()} @ {format_price(level_price)} ({amount:.8f})")
        
        logger.info(f"Grid setup complete:")
        logger.info(f"  Range: {format_price(self.state.lower_limit)} - {format_price(self.state.upper_limit)}")
        logger.info(f"  Grid step: {format_price(grid_step)}")
        logger.info(f"  Buy levels: {len(self.state.get_buy_levels())}")
        logger.info(f"  Sell levels: {len(self.state.get_sell_levels())}")
        logger.info(f"  Order size: ~{format_price(order_value)} each")
    
    def _place_initial_orders(self, current_price: float):
        """Place initial grid orders."""
        symbol = self.config.trading_pair
        
        for level in self.state.get_buy_levels():
            if level.status == "pending":
                try:
                    order = self.exchange.place_limit_buy(
                        symbol=symbol,
                        amount=level.amount,
                        price=level.price,
                    )
                    level.order_id = order.id
                    level.status = "active"
                except Exception as e:
                    logger.warning(f"Could not place buy at {format_price(level.price)}: {e}")
        
        base_balance = self.exchange.get_balance(self.config.base_currency)
        if base_balance > 0:
            sell_levels = self.state.get_sell_levels()
            if sell_levels:
                amount_per_level = base_balance / len(sell_levels)
                for level in sell_levels:
                    if level.status == "pending" and amount_per_level > 0:
                        try:
                            level.amount = amount_per_level
                            order = self.exchange.place_limit_sell(
                                symbol=symbol,
                                amount=level.amount,
                                price=level.price,
                            )
                            level.order_id = order.id
                            level.status = "active"
                        except Exception as e:
                            logger.warning(f"Could not place sell at {format_price(level.price)}: {e}")
        
        active = len(self.state.get_active_orders())
        logger.info(f"Placed {active} initial orders")
    
    def check_and_update(self) -> bool:
        """
        Main loop iteration: check orders and update grid.
        
        Returns False if trading should stop (panic triggered).
        """
        logger.debug("LOOP: check_and_update() called")
        
        if not self.is_running or self.panic_triggered:
            logger.debug(f"  Skipping: is_running={self.is_running}, panic_triggered={self.panic_triggered}")
            return False
        
        symbol = self.config.trading_pair
        
        try:
            current_price = self.exchange.get_ticker_price(symbol)
            logger.debug(f"  Current price: {format_price(current_price)}")
        except Exception as e:
            logger.error(f"Failed to get price: {e}")
            return True
        
        risk = self.risk_manager.assess_risk(current_price)
        logger.debug(f"  Risk level: {risk.level.value}")
        
        if risk.level == RiskLevel.PANIC:
            logger.warning(risk.message)
            self.panic_triggered = True
            self.risk_manager.execute_panic_sell()
            return False
        
        if risk.level == RiskLevel.WARNING:
            logger.warning(risk.message)
        
        active_orders = self.state.get_active_orders()
        logger.debug(f"  Checking {len(active_orders)} active orders...")
        
        for level in active_orders:
            if level.order_id is None:
                continue
            
            try:
                order = self.exchange.get_order_status(level.order_id, symbol)
                
                if order.is_filled:
                    self._handle_filled_order(level, order, current_price)
                    
            except Exception as e:
                logger.error(f"Error checking order {level.order_id}: {e}")
        
        return True
    
    def _handle_filled_order(self, level: GridLevel, order: Order, current_price: float):
        """Handle a filled order by placing the counter order."""
        symbol = self.config.trading_pair
        level.status = "filled"
        
        grid_step = (self.state.upper_limit - self.state.lower_limit) / self.config.grid_count
        
        if order.side == "buy":
            sell_price = level.price + grid_step
            
            if sell_price <= self.state.upper_limit:
                try:
                    new_order = self.exchange.place_limit_sell(
                        symbol=symbol,
                        amount=order.amount,
                        price=sell_price,
                    )
                    
                    new_level = GridLevel(
                        price=sell_price,
                        side="sell",
                        order_id=new_order.id,
                        status="active",
                        amount=order.amount,
                    )
                    self.state.levels.append(new_level)
                    
                    logger.info(f"Buy filled → Sell placed at {format_price(sell_price)}")
                except Exception as e:
                    logger.error(f"Failed to place counter sell: {e}")
        
        elif order.side == "sell":
            buy_price = level.price - grid_step
            
            if buy_price >= self.state.lower_limit:
                if not self.risk_manager.should_stop_buying(current_price):
                    try:
                        order_value = self.config.order_size
                        amount = order_value / buy_price
                        
                        new_order = self.exchange.place_limit_buy(
                            symbol=symbol,
                            amount=amount,
                            price=buy_price,
                        )
                        
                        new_level = GridLevel(
                            price=buy_price,
                            side="buy",
                            order_id=new_order.id,
                            status="active",
                            amount=amount,
                        )
                        self.state.levels.append(new_level)
                        
                        logger.info(f"Sell filled → Buy placed at {format_price(buy_price)}")
                    except Exception as e:
                        logger.error(f"Failed to place counter buy: {e}")
                else:
                    logger.warning(f"Skipping buy at {format_price(buy_price)} - risk too high")
    
    def stop(self):
        """Stop the strategy and cancel all orders."""
        self.is_running = False
        
        canceled = self.exchange.cancel_all_orders(self.config.trading_pair)
        logger.info(f"Strategy stopped, canceled {canceled} orders")
    
    def get_status(self) -> dict:
        """Get current strategy status."""
        active_orders = self.state.get_active_orders()
        buy_orders = [o for o in active_orders if o.side == "buy"]
        sell_orders = [o for o in active_orders if o.side == "sell"]
        
        return {
            "is_running": self.is_running,
            "panic_triggered": self.panic_triggered,
            "initial_price": self.state.initial_price,
            "upper_limit": self.state.upper_limit,
            "lower_limit": self.state.lower_limit,
            "active_buy_orders": len(buy_orders),
            "active_sell_orders": len(sell_orders),
            "total_levels": len(self.state.levels),
        }
