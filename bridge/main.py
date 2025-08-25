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
from typing import Dict, List, Set
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
        self.previous_position_tickets = set()  # Track positions from previous iteration

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
                    
                    # Initialize previous_position_tickets with current positions
                    if positions:
                        self.previous_position_tickets = {pos.get('ticket') for pos in positions if pos.get('ticket')}
                        logger.info(f"Initialized with {len(self.previous_position_tickets)} existing positions")
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

    def detect_closed_positions(self, current_positions: List[Dict]):
        """
        Detect positions that have closed by comparing current vs previous positions.
        Move closed positions to trade history.
        
        Args:
            current_positions: List of current open positions from MT5
        """
        if not self.supabase_client:
            return
            
        try:
            # Get current position tickets
            current_tickets = {pos.get('ticket') for pos in current_positions if pos.get('ticket')}
            
            # Find tickets that were open before but are not open now (closed positions)
            closed_tickets = self.previous_position_tickets - current_tickets
            
            if closed_tickets:
                logger.info(f"Detected {len(closed_tickets)} closed positions: {list(closed_tickets)}")
                
                # For each closed position, we need to get the final state and move to history
                # Since the position is no longer in MT5, we need to get it from our database or deal history
                for ticket in closed_tickets:
                    try:
                        # Try to get the final trade state from recent deals
                        self.handle_closed_position(ticket)
                    except Exception as e:
                        logger.error(f"Error handling closed position {ticket}: {e}")
                
                # Clean up closed positions from the positions table
                remaining_tickets = list(current_tickets)
                self.supabase_client.cleanup_old_positions(remaining_tickets)
                
            # Update previous tickets for next iteration
            self.previous_position_tickets = current_tickets
            
        except Exception as e:
            logger.error(f"Error detecting closed positions: {e}")

    def handle_closed_position(self, ticket: int):
        """
        Handle a single closed position by finding its final state and moving to history.
        
        Args:
            ticket: The ticket number of the closed position
        """
        try:
            # Get recent deals to find the closing deal for this position
            recent_deals = self.mt5_client.get_deals_history()
            
            # Look for the closing deal for this position
            closing_deal = None
            for deal in recent_deals:
                # Check if this deal closes our position
                if (hasattr(deal, 'position_id') and deal.position_id == ticket and 
                    hasattr(deal, 'entry') and deal.entry == 1):  # DEAL_ENTRY_OUT
                    closing_deal = deal
                    break
                elif (hasattr(deal, 'ticket') and deal.ticket == ticket and
                      hasattr(deal, 'entry') and deal.entry == 1):  # Alternative check
                    closing_deal = deal
                    break
            
            if closing_deal:
                # Convert the closing deal to our trade format
                closed_trade_data = {
                    'ticket': ticket,
                    'symbol': getattr(closing_deal, 'symbol', ''),
                    'type': getattr(closing_deal, 'type', 0),  # Keep as integer for conversion
                    'volume': float(getattr(closing_deal, 'volume', 0)),
                    'price': float(getattr(closing_deal, 'price', 0)),
                    'profit': float(getattr(closing_deal, 'profit', 0)),
                    'swap': float(getattr(closing_deal, 'swap', 0)),
                    'commission': float(getattr(closing_deal, 'commission', 0)),
                    'comment': getattr(closing_deal, 'comment', 'Position closed')
                }
                
                # Move to history (records CLOSE event and removes from positions)
                self.supabase_client.move_to_history(closed_trade_data)
                logger.info(f"Successfully moved closed position {ticket} to history")
                
            else:
                logger.warning(f"Could not find closing deal for position {ticket}")
                # Fallback: Remove from positions table without detailed close data
                self.supabase_client.cleanup_old_positions([])  # Will remove this specific position
                
        except Exception as e:
            logger.error(f"Error handling closed position {ticket}: {e}")

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
                        
                        # Detect closed positions BEFORE updating current positions
                        if self.supabase_client:
                            self.detect_closed_positions(positions)
                        
                        # Update current positions in Supabase
                        if self.supabase_client:
                            self.supabase_client.upsert_positions(positions)
                            logger.debug(f"Updated {len(positions)} positions in Supabase")
                    else:
                        logger.debug("No open positions found")
                        
                        # If no positions now but we had some before, they're all closed
                        if self.previous_position_tickets and self.supabase_client:
                            logger.info("All positions have been closed")
                            self.detect_closed_positions([])  # Empty list = all closed
                            
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