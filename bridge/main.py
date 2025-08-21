#!/usr/bin/env python3
"""
MT5 to Supabase Bridge - Production Implementation
Monitors MT5 positions and trades, syncing to Supabase with realtime updates
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Set, List, Dict, Optional
from dotenv import load_dotenv

from mt5_client import MT5Client
from supabase_client import SupabaseClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bridge.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MT5Bridge:
    def __init__(self):
        self.mt5_client = MT5Client()
        self.supabase_client = SupabaseClient()
        self.seen_open_tickets: Set[int] = set()
        self.update_interval = float(os.getenv('UPDATE_MS', 1000)) / 1000
        self.max_retries = 3
        self.base_delay = 1
        self.is_running = False
        
    def initialize(self) -> bool:
        """Initialize both MT5 and Supabase connections"""
        try:
            logger.info("Initializing MT5 Bridge...")
            
            # Initialize MT5
            if not self.mt5_client.initialize_mt5():
                logger.error("Failed to initialize MT5")
                return False
                
            # Test Supabase connection
            if not self.supabase_client.test_connection():
                logger.error("Failed to connect to Supabase")
                return False
                
            logger.info("Bridge initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    def detect_closes(self, current_tickets: Set[int]) -> Set[int]:
        """
        Detect positions that were open but are now closed
        Returns tickets that were in seen_open_tickets but not in current_tickets
        """
        closed_tickets = self.seen_open_tickets - current_tickets
        if closed_tickets:
            logger.info(f"Detected {len(closed_tickets)} closed positions: {closed_tickets}")
        return closed_tickets
    
    def process_closed_tickets(self, closed_tickets: Set[int]) -> None:
        """
        Process closed positions by fetching their close data from MT5 history
        and inserting trade records with action='CLOSE'
        """
        if not closed_tickets:
            return
            
        try:
            # Get recent closed deals from MT5 history
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)  # Look back 1 hour for closes
            
            closed_deals = self.mt5_client.get_closed_deals_since(start_time)
            
            # Filter deals that match our closed tickets
            matching_deals = [
                deal for deal in closed_deals 
                if deal.get('position_id') in closed_tickets
            ]
            
            # Insert trade records for each close
            for deal in matching_deals:
                trade_data = {
                    'ticket': deal['position_id'],
                    'action': 'CLOSE',
                    'symbol': deal['symbol'],
                    'type': deal['type'],
                    'volume': deal['volume'],
                    'price': deal['price'],
                    'profit': deal.get('profit', 0),
                    'swap': deal.get('swap', 0),
                    'commission': deal.get('commission', 0),
                    'comment': deal.get('comment', ''),
                    'timestamp': datetime.fromtimestamp(deal['time']).isoformat()
                }
                
                success = self.supabase_client.append_trade(trade_data)
                if success:
                    logger.info(f"Recorded close for ticket {deal['position_id']}")
                else:
                    logger.warning(f"Failed to record close for ticket {deal['position_id']}")
                    
        except Exception as e:
            logger.error(f"Error processing closed tickets: {e}")
    
    def process_new_opens(self, current_positions: List[Dict]) -> None:
        """
        Process newly opened positions by checking if they're new
        and inserting trade records with action='OPEN'
        """
        try:
            current_tickets = {pos['ticket'] for pos in current_positions}
            new_tickets = current_tickets - self.seen_open_tickets
            
            if new_tickets:
                logger.info(f"Detected {len(new_tickets)} new positions: {new_tickets}")
                
                # Find the new position data and record opens
                for position in current_positions:
                    if position['ticket'] in new_tickets:
                        trade_data = {
                            'ticket': position['ticket'],
                            'action': 'OPEN',
                            'symbol': position['symbol'],
                            'type': position['type'],
                            'volume': position['volume'],
                            'price': position['price_open'],
                            'profit': None,  # No profit on open
                            'swap': position.get('swap', 0),
                            'commission': position.get('commission', 0),
                            'comment': position.get('comment', ''),
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        success = self.supabase_client.append_trade(trade_data)
                        if success:
                            logger.info(f"Recorded open for ticket {position['ticket']}")
                        else:
                            logger.warning(f"Failed to record open for ticket {position['ticket']}")
                            
        except Exception as e:
            logger.error(f"Error processing new opens: {e}")
    
    def send_heartbeat(self) -> None:
        """Send heartbeat to indicate bridge is alive"""
        try:
            heartbeat_data = {
                'id': 1,
                'last_seen': datetime.now().isoformat(),
                'status': 'healthy',
                'positions_count': len(self.seen_open_tickets)
            }
            self.supabase_client.send_heartbeat(heartbeat_data)
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")
    
    def handle_error(self, error: Exception, retry_count: int) -> bool:
        """
        Handle errors with exponential backoff
        Returns True if should continue, False if should stop
        """
        delay = self.base_delay * (2 ** retry_count)
        logger.error(f"Error (retry {retry_count}/{self.max_retries}): {error}")
        
        if retry_count >= self.max_retries:
            logger.error("Max retries reached, stopping bridge")
            return False
        
        logger.info(f"Waiting {delay} seconds before retry...")
        time.sleep(delay)
        
        # Try to reinitialize connections
        logger.info("Attempting to reinitialize connections...")
        return self.initialize()
    
    def main_loop(self) -> None:
        """Main processing loop"""
        self.is_running = True
        retry_count = 0
        last_heartbeat = datetime.now()
        heartbeat_interval = 30  # seconds
        
        logger.info(f"Starting main loop with {self.update_interval}s intervals")
        
        while self.is_running:
            try:
                # 1. Get current open positions from MT5
                current_positions = self.mt5_client.get_open_positions()
                current_tickets = {pos['ticket'] for pos in current_positions}
                
                # 2. Detect and process closed positions
                closed_tickets = self.detect_closes(current_tickets)
                self.process_closed_tickets(closed_tickets)
                
                # 3. Detect and process newly opened positions
                self.process_new_opens(current_positions)
                
                # 4. Upsert current positions to Supabase
                if current_positions:
                    success = self.supabase_client.upsert_positions(current_positions)
                    if not success:
                        logger.warning("Failed to upsert positions")
                
                # 5. Update seen tickets
                self.seen_open_tickets = current_tickets
                
                # 6. Send periodic heartbeat
                now = datetime.now()
                if (now - last_heartbeat).seconds >= heartbeat_interval:
                    self.send_heartbeat()
                    last_heartbeat = now
                
                # Reset retry count on successful iteration
                retry_count = 0
                
                # Wait for next iteration
                time.sleep(self.update_interval)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                self.is_running = False
                break
                
            except Exception as e:
                retry_count += 1
                if not self.handle_error(e, retry_count):
                    self.is_running = False
                    break
    
    def shutdown(self) -> None:
        """Graceful shutdown"""
        logger.info("Shutting down MT5 Bridge...")
        self.is_running = False
        
        try:
            # Send final heartbeat with offline status
            heartbeat_data = {
                'id': 1,
                'last_seen': datetime.now().isoformat(),
                'status': 'offline',
                'positions_count': len(self.seen_open_tickets)
            }
            self.supabase_client.send_heartbeat(heartbeat_data)
        except Exception as e:
            logger.warning(f"Failed to send shutdown heartbeat: {e}")
        
        # Cleanup MT5 connection
        self.mt5_client.shutdown()
        logger.info("Bridge shutdown complete")

def main():
    """Main entry point"""
    bridge = MT5Bridge()
    
    try:
        # Initialize the bridge
        if not bridge.initialize():
            logger.error("Failed to initialize bridge, exiting...")
            return 1
        
        # Run the main loop
        bridge.main_loop()
        
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        return 1
        
    finally:
        # Ensure cleanup happens
        bridge.shutdown()
    
    return 0

if __name__ == "__main__":
    exit(main())