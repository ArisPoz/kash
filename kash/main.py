"""Main entry point for Kash Grid Trading Bot."""

import argparse
import signal
import sys
import time

from .config import TradingConfig, get_config
from .exchange import create_exchange
from .grid_strategy import GridStrategy
from .risk_manager import RiskManager
from .simulator import SimulatedExchange
from .utils import logger, setup_logging
from .web_ui import run_web_ui, set_bot_instance


class KashBot:
    """Main bot controller."""
    
    def __init__(self, config: TradingConfig, web_ui: bool = True, web_port: int = 8080):
        self.config = config
        self.exchange = create_exchange(config)
        self.risk_manager = RiskManager(config, self.exchange)
        self.strategy = GridStrategy(config, self.exchange, self.risk_manager)
        self.should_stop = False
        self.web_ui_enabled = web_ui
        self.web_port = web_port
        
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown on SIGINT/SIGTERM."""
        logger.info("\nShutdown signal received...")
        self.should_stop = True
    
    def run(self):
        """Main bot loop."""
        logger.info("=" * 50)
        logger.info("KASH GRID TRADING BOT")
        logger.info("=" * 50)
        logger.info(f"Mode: {self.config.trading_mode.upper()}")
        logger.info(f"Pair: {self.config.trading_pair}")
        logger.info(f"Investment: €{self.config.investment:,.2f}")
        logger.info(f"Grid levels: {self.config.grid_count}")
        logger.info(f"Grid range: ±{self.config.grid_range_percent}%")
        logger.info(f"Stop loss: {self.config.stop_loss_percent}%")
        logger.info("=" * 50)
        
        if not self.strategy.initialize():
            logger.error("Failed to initialize strategy. Exiting.")
            return 1
        
        # Start web UI if enabled
        if self.web_ui_enabled:
            set_bot_instance(self)
            run_web_ui(port=self.web_port)
        
        logger.info(f"Bot running. Checking every {self.config.check_interval_seconds}s. Press Ctrl+C to stop.")
        
        iteration = 0
        while not self.should_stop:
            try:
                if not self.strategy.check_and_update():
                    logger.warning("Strategy stopped (panic triggered or error)")
                    break
                
                iteration += 1
                if iteration % 60 == 0:
                    self._print_status()
                
                time.sleep(self.config.check_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(self.config.check_interval_seconds)
        
        self._shutdown()
        return 0
    
    def _print_status(self):
        """Print periodic status update."""
        status = self.strategy.get_status()
        current_price = self.exchange.get_ticker_price(self.config.trading_pair)
        
        logger.info("-" * 40)
        logger.info(f"Status: Price €{current_price:,.2f} | "
                   f"Buys: {status['active_buy_orders']} | "
                   f"Sells: {status['active_sell_orders']}")
        
        if isinstance(self.exchange, SimulatedExchange):
            self.exchange.print_summary()
    
    def _shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down...")
        self.strategy.stop()
        
        if isinstance(self.exchange, SimulatedExchange):
            self.exchange.print_summary()
        
        logger.info("Kash bot stopped.")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Kash - Grid Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m kash.main --simulation          Run in simulation mode
  python -m kash.main --live                Run with real trading
  python -m kash.main --pair ETH/USDT       Trade ETH instead of BTC
  python -m kash.main --grids 30            Use 30 grid levels
        """
    )
    
    parser.add_argument(
        "--simulation", "-s",
        action="store_true",
        help="Run in simulation mode (paper trading)"
    )
    parser.add_argument(
        "--live", "-l",
        action="store_true",
        help="Run in live trading mode (requires API keys)"
    )
    parser.add_argument(
        "--pair", "-p",
        type=str,
        help="Trading pair (e.g., BTC/USDT, ETH/USDT)"
    )
    parser.add_argument(
        "--investment", "-i",
        type=float,
        help="Investment amount in quote currency"
    )
    parser.add_argument(
        "--grids", "-g",
        type=int,
        help="Number of grid levels"
    )
    parser.add_argument(
        "--range", "-r",
        type=float,
        help="Grid range percentage (e.g., 10 for ±10%%)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging (shows all API calls and responses)"
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable web UI"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Web UI port (default: 8080)"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        setup_logging("DEBUG", log_file="kash_debug.log")
    elif args.verbose:
        setup_logging("DEBUG")
    
    try:
        config = TradingConfig.from_env()
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        return 1
    
    if args.simulation:
        config.trading_mode = "simulation"
    elif args.live:
        config.trading_mode = "live"
    
    if args.pair:
        config.trading_pair = args.pair
        base, quote = args.pair.split("/")
        config.base_currency = base
        config.quote_currency = quote
    
    if args.investment:
        config.investment = args.investment
    
    if args.grids:
        config.grid_count = args.grids
    
    if args.range:
        config.grid_range_percent = args.range
    
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Config error: {error}")
        return 1
    
    bot = KashBot(config, web_ui=not args.no_ui, web_port=args.port)
    return bot.run()


if __name__ == "__main__":
    sys.exit(main())
