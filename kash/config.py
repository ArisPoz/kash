"""Configuration module with safety parameters for grid trading."""

import os
from dataclasses import dataclass
from typing import Literal, cast
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TradingConfig:
    """Trading configuration with safety parameters."""
    
    exchange_id: str = "binance"
    api_key: str = ""
    api_secret: str = ""
    
    trading_pair: str = "BTC/EUR"
    base_currency: str = "BTC"
    quote_currency: str = "EUR"
    
    investment: float = 1000.0
    grid_count: int = 25
    grid_range_percent: float = 10.0
    stop_loss_percent: float = 15.0
    panic_sell_buffer: float = 5.0
    
    trading_mode: Literal["simulation", "live"] = "simulation"
    check_interval_seconds: int = 5
    
    @classmethod
    def from_env(cls) -> "TradingConfig":
        """Load configuration from environment variables."""
        pair = os.getenv("TRADING_PAIR", "BTC/USDT")
        base, quote = pair.split("/")
        
        return cls(
            exchange_id=os.getenv("EXCHANGE_ID", "binance"),
            api_key=os.getenv("API_KEY", ""),
            api_secret=os.getenv("API_SECRET", ""),
            trading_pair=pair,
            base_currency=base,
            quote_currency=quote,
            investment=float(os.getenv("INVESTMENT", "1000")),
            grid_count=int(os.getenv("GRID_COUNT", "20")),
            grid_range_percent=float(os.getenv("GRID_RANGE_PERCENT", "10")),
            stop_loss_percent=float(os.getenv("STOP_LOSS_PERCENT", "15")),
            trading_mode=cast(Literal["simulation", "live"], os.getenv("TRADING_MODE", "simulation")),
            check_interval_seconds=int(os.getenv("CHECK_INTERVAL", "10")),
        )
    
    @property
    def order_size(self) -> float:
        """Calculate size per grid order (investment / grid_count)."""
        return self.investment / self.grid_count
    
    @property
    def grid_spacing_percent(self) -> float:
        """Calculate spacing between grid levels."""
        return (self.grid_range_percent * 2) / self.grid_count
    
    def calculate_grid_levels(self, current_price: float) -> tuple[list[float], list[float]]:
        """
        Calculate buy and sell grid levels based on current price.
        
        Returns:
            Tuple of (buy_levels, sell_levels) - prices for each grid
        """
        upper_limit = current_price * (1 + self.grid_range_percent / 100)
        lower_limit = current_price * (1 - self.grid_range_percent / 100)
        
        grid_step = (upper_limit - lower_limit) / self.grid_count
        
        buy_levels = []
        sell_levels = []
        
        for i in range(self.grid_count):
            level_price = lower_limit + (i * grid_step)
            if level_price < current_price:
                buy_levels.append(level_price)
            else:
                sell_levels.append(level_price)
        
        return buy_levels, sell_levels
    
    def get_panic_sell_price(self, current_price: float) -> float:
        """Calculate panic sell trigger price."""
        lower_limit = current_price * (1 - self.grid_range_percent / 100)
        return lower_limit * (1 - self.panic_sell_buffer / 100)
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if self.investment < 100:
            errors.append("Investment must be at least €100")
        
        if self.grid_count < 5 or self.grid_count > 100:
            errors.append("Grid count must be between 5 and 100")
        
        if self.grid_range_percent < 2 or self.grid_range_percent > 50:
            errors.append("Grid range must be between 2% and 50%")
        
        if self.order_size < 10:
            errors.append(f"Order size (€{self.order_size:.2f}) too small. Reduce grid count or increase investment.")
        
        if self.trading_mode == "live" and (not self.api_key or not self.api_secret):
            errors.append("API credentials required for live trading")
        
        return errors


def get_config() -> TradingConfig:
    """Get validated configuration."""
    config = TradingConfig.from_env()
    errors = config.validate()
    if errors:
        raise ValueError(f"Configuration errors: {'; '.join(errors)}")
    return config
