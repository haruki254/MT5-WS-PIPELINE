#!/usr/bin/env python3
"""
MT5 to Supabase Bridge
Streams MT5 positions and trades to Supabase in real-time
"""

import os
import time
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, List
from dotenv import load_dotenv
from mt5_client import MT5Client
from supabase_client import SupabaseClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.getenv('LOG_FILE', 'bridge.log')),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class MT5Bridge:
    def __init__(self):
        self.mt5_client = None
        self.supabase_client = None
        self.running = False
        self.update_interval = int(os.getenv('UPDATE_MS', 1000)) / 1000  # Convert to seconds

    def initialize(self):
        """Initialize MT5 and Supabase connections"""
        try:
            logger.info("Initializing MT5 Bridge...")
            
            # Initialize MT5 Client
            logger.info("Creating MT5 client...")
            self.mt5_client = MT5Client()
            
            # Check if MT5Client has initialize method, if not handle gracefully
            if hasattr(self.mt5_client, 'initialize'):
                logger.info("Using MT5Client initialize method...")
                if not self.mt5_client.initialize():
                    raise Exception("Failed to initialize MT5 - initialize method returned False")
            else:
                # If no initialize method, try to call MT5 directly
                logger.info("No initialize method found, trying direct MT5 initialization...")
                import MetaTrader5 as mt5
                if not mt5.initialize():
                    error = mt5.last_error()
                    raise Exception(f"Failed to initialize MT5 directly: {error}")
                logger.info("MT5 initialized directly (no client initialize method)")
            
            # Verify MT5 is working by checking if we can get basic info
            try:
                if hasattr(self.mt5_client, 'get_positions'):
                    logger.info("Testing MT5 connection by getting positions...")
                    positions = self.mt5_client.get_positions()
                    logger.info(f"MT5 connection test successful - found {len(positions) if positions else 0} positions")
                else:
                    logger.warning("MT5Client missing get_positions method")
            except Exception as e:
                logger.warning(f"MT5 connection test failed: {e}")
            
            # Initialize Supabase
            logger.info("Initializing Supabase client...")
            self.supabase_client = SupabaseClient()
            
            # Test Supabase connection by sending a heartbeat
            try:
                self.supabase_client.send_heartbeat()
                logger.info("Supabase connection verified")
            except Exception as e:
                logger.warning(f"Could not verify Supabase connection: {e}")
                # Don't fail initialization if heartbeat fails, just warn
            
            logger.info("Bridge initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            logger.error("Please check:")
            logger.error("1. MT5 terminal is running and logged in")
            logger.error("2. MT5 allows automated trading")
            logger.error("3. Python mt5_client.py file exists and has proper methods")
            logger.error("4. Supabase credentials are correct")
            return False

    def run(self):
        """Main bridge loop"""
        if not self.initialize():
            logger.error("Failed to initialize bridge, exiting...")
            return

        self.running = True
        logger.info("Starting bridge main loop...")

        try:
            while self.running:
                start_time = time.time()
                
                # Get current positions
                try:
                    positions = self.mt5_client.get_positions()
                    if positions:
                        logger.info(f"Found {len(positions)} open positions")
                        for pos in positions:
                            logger.info(f"Position: {pos.get('symbol', 'N/A')} - {pos.get('type', 'N/A')} - Volume: {pos.get('volume', 'N/A')} - P&L: {pos.get('profit', 'N/A')}")
                        
                        # Update positions in Supabase (if available)
                        if self.supabase_client:
                            self.supabase_client.upsert_positions(positions)
                            logger.debug(f"Updated {len(positions)} positions in Supabase")
                    else:
                        logger.debug("No open positions found")
                except Exception as e:
                    logger.error(f"Error getting/updating positions: {e}")
                
                # Check for new trades (if Supabase is available)
                if self.supabase_client:
                    try:
                        self.check_for_new_trades()
                    except Exception as e:
                        logger.error(f"Error checking for new trades: {e}")
                else:
                    logger.debug("Skipping trade history check (Supabase disabled)")
                
                # Send heartbeat every 10 iterations (10 seconds if UPDATE_MS=1000)
                if hasattr(self, '_heartbeat_counter'):
                    self._heartbeat_counter += 1
                else:
                    self._heartbeat_counter = 1
                
                if self._heartbeat_counter >= 10:
                    if self.supabase_client:
                        try:
                            self.supabase_client.send_heartbeat()
                            logger.debug("Heartbeat sent")
                        except Exception as e:
                            logger.warning(f"Failed to send heartbeat: {e}")
                    else:
                        logger.debug("Skipping heartbeat (Supabase disabled)")
                    self._heartbeat_counter = 0
                
                # Sleep for remaining interval time
                elapsed = time.time() - start_time
                sleep_time = max(0, self.update_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Bridge error: {e}")
        finally:
            self.shutdown()

    def check_for_new_trades(self):
        """Check for new trades and log them"""
        if not self.supabase_client:
            logger.debug("Supabase client not available, skipping trade history check")
            return
            
        try:
            # Get the last close check timestamp
            last_check = self.supabase_client.get_last_close_check()
            
            # Get trade history since last check
            trades = self.mt5_client.get_deals_history(last_check)
            
            if trades:
                logger.info(f"Found {len(trades)} new trades")
                processed_count = 0
                skipped_count = 0
                
                for trade in trades:
                    # Debug: Print trade structure to understand what fields are available
                    logger.debug(f"Raw trade data: {trade}")
                    logger.debug(f"Trade type: {type(trade)}")
                    if hasattr(trade, '__dict__'):
                        logger.debug(f"Trade attributes: {trade.__dict__}")
                    
                    # Transform MT5 trade data to match our database schema
                    try:
                        # Convert MT5 trade to our format
                        formatted_trade = self.format_mt5_trade(trade)
                        
                        # Only append if formatting was successful (not None)
                        if formatted_trade is not None:
                            # Append each trade to the database
                            self.supabase_client.append_trade(formatted_trade)
                            processed_count += 1
                            logger.info(f"Processed trade: {formatted_trade['ticket']} - {formatted_trade['action']} - {formatted_trade['symbol']}")
                        else:
                            skipped_count += 1
                            logger.warning(f"Skipped trade due to formatting issues")
                            
                    except Exception as e:
                        logger.error(f"Error formatting/appending trade: {e}")
                        logger.error(f"Trade data: {trade}")
                        skipped_count += 1
                
                logger.info(f"Trade processing complete: {processed_count} processed, {skipped_count} skipped")
                
                # Update the last close check timestamp
                current_time = datetime.now(timezone.utc)
                self.supabase_client.update_last_close_check(current_time)
                
        except Exception as e:
            logger.error(f"Error checking for new trades: {e}")

    def format_mt5_trade(self, mt5_trade):
        """
        Convert MT5 trade/deal data to our database format.
        MT5 deals have different field names than our expected format.
        """
        # MT5 deal/trade typically has these fields:
        # - ticket: deal ticket
        # - order: order ticket
        # - time: deal time
        # - type: deal type (0=buy, 1=sell, etc.)
        # - entry: entry type (0=in, 1=out, 2=inout, 3=out_by)
        # - volume: volume
        # - price: deal price
        # - profit: profit
        # - swap: swap
        # - commission: commission
        # - symbol: symbol
        # - comment: comment
        
        try:
            # Determine action based on MT5 deal entry type
            action = 'UNKNOWN'  # Default fallback
            
            if hasattr(mt5_trade, 'entry'):
                entry_value = mt5_trade.entry
                logger.debug(f"Processing trade with entry value: {entry_value}")
                
                if entry_value == 0:  # DEAL_ENTRY_IN
                    action = 'OPEN'
                elif entry_value == 1:  # DEAL_ENTRY_OUT  
                    action = 'CLOSE'
                elif entry_value == 2:  # DEAL_ENTRY_INOUT (reversal)
                    # For reversals, we could treat as both CLOSE and OPEN
                    # For now, treat as CLOSE since it closes the previous position
                    action = 'CLOSE'
                    logger.info(f"Trade {getattr(mt5_trade, 'ticket', 'N/A')} is a position reversal (entry=2)")
                elif entry_value == 3:  # DEAL_ENTRY_OUT_BY (closed by opposite)
                    action = 'CLOSE'
                    logger.info(f"Trade {getattr(mt5_trade, 'ticket', 'N/A')} was closed by opposite position (entry=3)")
                else:
                    logger.warning(f"Unknown entry type {entry_value} for trade {getattr(mt5_trade, 'ticket', 'N/A')}")
                    action = 'UNKNOWN'
            else:
                # No entry field available, try to determine from context
                logger.warning(f"Trade {getattr(mt5_trade, 'ticket', 'N/A')} has no entry field")
                # You might want to add additional logic here based on other fields
                # For now, skip trades without entry information
                action = 'UNKNOWN'
            
            # Skip trades where we can't determine the action
            if action == 'UNKNOWN':
                logger.warning(f"Skipping trade {getattr(mt5_trade, 'ticket', 'N/A')} - cannot determine action")
                return None
            
            # Get trade type (buy/sell)
            if hasattr(mt5_trade, 'type'):
                trade_type = 'buy' if mt5_trade.type == 0 else 'sell'
            else:
                trade_type = 'unknown'
            
            # Build formatted trade data
            formatted_trade = {
                'ticket': getattr(mt5_trade, 'ticket', getattr(mt5_trade, 'order', 0)),
                'action': action,
                'symbol': getattr(mt5_trade, 'symbol', ''),
                'type': trade_type,
                'volume': float(getattr(mt5_trade, 'volume', 0)),
                'price': float(getattr(mt5_trade, 'price', 0)),
                'profit': float(getattr(mt5_trade, 'profit', 0)),
                'swap': float(getattr(mt5_trade, 'swap', 0)),
                'commission': float(getattr(mt5_trade, 'commission', 0)),
                'comment': getattr(mt5_trade, 'comment', ''),
                'timestamp': None  # Let the database function handle timestamp
            }
            
            # Handle timestamp if available
            if hasattr(mt5_trade, 'time'):
                if isinstance(mt5_trade.time, (int, float)):
                    # Convert Unix timestamp to ISO format
                    formatted_trade['timestamp'] = datetime.fromtimestamp(
                        mt5_trade.time, tz=timezone.utc
                    ).isoformat()
                else:
                    # Assume it's already a datetime or string
                    formatted_trade['timestamp'] = str(mt5_trade.time)
            
            logger.debug(f"Formatted trade: ticket={formatted_trade['ticket']}, action={formatted_trade['action']}, symbol={formatted_trade['symbol']}")
            return formatted_trade
            
        except Exception as e:
            logger.error(f"Error formatting MT5 trade: {e}")
            logger.error(f"MT5 trade data: {mt5_trade}")
            raise

    def shutdown(self):
        """Clean shutdown"""
        logger.info("Shutting down MT5 Bridge...")
        self.running = False
        
        # Send final heartbeat
        if self.supabase_client:
            try:
                self.supabase_client.send_heartbeat()
                logger.debug("Shutdown heartbeat sent")
            except Exception as e:
                logger.warning(f"Failed to send shutdown heartbeat: {e}")
        
        # Cleanup MT5
        if self.mt5_client:
            # Check if MT5 client has shutdown method
            if hasattr(self.mt5_client, 'shutdown'):
                self.mt5_client.shutdown()
            else:
                # Try direct MT5 shutdown
                try:
                    import MetaTrader5 as mt5
                    mt5.shutdown()
                    logger.info("MT5 shutdown directly")
                except Exception as e:
                    logger.warning(f"Failed to shutdown MT5 directly: {e}")
        
        logger.info("Bridge shutdown complete")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    if 'bridge' in globals():
        bridge.shutdown()
    sys.exit(0)

def main():
    """Main entry point"""
    global bridge
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run bridge
    bridge = MT5Bridge()
    bridge.run()

if __name__ == "__main__":
    main()