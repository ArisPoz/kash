"""Risk management with stop loss and panic sell functionality."""

from dataclasses import dataclass
from enum import Enum

from .config import TradingConfig
from .exchange import ExchangeInterface
from .utils import logger, format_price, format_percent


class RiskLevel(Enum):
    """Risk assessment levels."""
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"
    PANIC = "panic"


@dataclass
class RiskAssessment:
    """Result of risk evaluation."""
    level: RiskLevel
    current_price: float
    lower_limit: float
    panic_price: float
    price_vs_lower: float
    message: str


class RiskManager:
    """Manages risk thresholds and emergency actions."""
    
    def __init__(self, config: TradingConfig, exchange: ExchangeInterface):
        self.config = config
        self.exchange = exchange
        self.initial_price: float | None = None
        self.lower_limit: float | None = None
        self.panic_price: float | None = None
    
    def initialize(self, current_price: float):
        """Set initial price levels for risk monitoring."""
        self.initial_price = current_price
        self.lower_limit = current_price * (1 - self.config.grid_range_percent / 100)
        self.panic_price = self.config.get_panic_sell_price(current_price)
        
        logger.info(f"Risk Manager initialized:")
        logger.info(f"  Initial price: {format_price(current_price)}")
        logger.info(f"  Lower limit (stop buying): {format_price(self.lower_limit)}")
        logger.info(f"  Panic sell trigger: {format_price(self.panic_price)}")
    
    def assess_risk(self, current_price: float) -> RiskAssessment:
        """Evaluate current risk level based on price."""
        if self.lower_limit is None or self.panic_price is None:
            self.initialize(current_price)
        
        price_vs_lower = ((current_price - self.lower_limit) / self.lower_limit) * 100
        
        if current_price <= self.panic_price:
            level = RiskLevel.PANIC
            message = f"PANIC: Price {format_price(current_price)} below panic threshold!"
        elif current_price <= self.lower_limit:
            level = RiskLevel.DANGER
            message = f"DANGER: Price {format_price(current_price)} below lower limit - stop buying"
        elif current_price <= self.lower_limit * 1.02:
            level = RiskLevel.WARNING
            message = f"WARNING: Price approaching lower limit ({format_percent(price_vs_lower)} above)"
        else:
            level = RiskLevel.SAFE
            message = f"Safe: Price {format_percent(price_vs_lower)} above lower limit"
        
        return RiskAssessment(
            level=level,
            current_price=current_price,
            lower_limit=self.lower_limit,
            panic_price=self.panic_price,
            price_vs_lower=price_vs_lower,
            message=message,
        )
    
    def should_stop_buying(self, current_price: float) -> bool:
        """Check if we should stop placing new buy orders."""
        assessment = self.assess_risk(current_price)
        return assessment.level in (RiskLevel.DANGER, RiskLevel.PANIC)
    
    def should_panic_sell(self, current_price: float) -> bool:
        """Check if panic sell should be triggered."""
        assessment = self.assess_risk(current_price)
        return assessment.level == RiskLevel.PANIC
    
    def execute_panic_sell(self) -> bool:
        """
        Emergency: Cancel all orders and sell all holdings at market.
        
        Returns True if panic sell was executed.
        """
        logger.warning("=" * 50)
        logger.warning("EXECUTING PANIC SELL - EMERGENCY LIQUIDATION")
        logger.warning("=" * 50)
        
        symbol = self.config.trading_pair
        
        canceled = self.exchange.cancel_all_orders(symbol)
        logger.info(f"Canceled {canceled} open orders")
        
        base_balance = self.exchange.get_balance(self.config.base_currency)
        
        if base_balance > 0:
            try:
                current_price = self.exchange.get_ticker_price(symbol)
                self.exchange.place_limit_sell(
                    symbol=symbol,
                    amount=base_balance,
                    price=current_price * 0.995,
                )
                logger.warning(f"Panic sell order placed for {base_balance:.6f} {self.config.base_currency}")
            except Exception as e:
                logger.error(f"Failed to execute panic sell: {e}")
                return False
        
        logger.warning("Panic sell complete - bot will stop trading")
        return True
    
    def recalibrate(self, new_price: float):
        """
        Recalibrate risk levels to new price.
        Use this when manually restarting after a significant price move.
        """
        old_lower = self.lower_limit
        self.initialize(new_price)
        logger.info(f"Risk levels recalibrated from {format_price(old_lower)} to {format_price(self.lower_limit)}")
