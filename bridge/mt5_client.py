"""
MT5 Client for connecting to MetaTrader 5 and fetching trading data.
Handles initialization, position retrieval, account info, and closed deals tracking.
"""

import MetaTrader5 as mt5
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MT5Client:
    """MetaTrader 5 client for trading data retrieval."""
    
    def __init__(self):
        """Initialize MT5 client with environment variables."""
        self.login = int(os.getenv('MT5_LOGIN', 0))
        self.password = os.getenv('MT5_PASSWORD', '')
        self.server = os.getenv('MT5_SERVER', '')
        self.is_initialized = False
        
    def initialize_mt5(self) -> bool:
        """
        Initialize connection to MT5 terminal.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            # Initialize MT5 connection
            if not mt5.initialize():
                logger.error(f"MT5 initialize() failed: {mt5.last_error()}")
                return False
            
            # Login to trading account
            if not mt5.login(self.login, password=self.password, server=self.server):
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                mt5.shutdown()
                return False
            
            self.is_initialized = True
            logger.info(f"Successfully connected to MT5 account {self.login} on {self.server}")
            return True
            
        except Exception as e:
            logger.error(f"Exception during MT5 initialization: {e}")
            return False
    
    def _ensure_connection(self) -> bool:
        """
        Ensure MT5 connection is active, reinitialize if needed.
        
        Returns:
            bool: True if connection is active, False otherwise
        """
        if not self.is_initialized:
            return self.initialize_mt5()
        
        # Test connection by getting account info
        try:
            account_info = mt5.account_info()
            if account_info is None:
                logger.warning("MT5 connection lost, reinitializing...")
                self.is_initialized = False
                return self.initialize_mt5()
            return True
        except Exception as e:
            logger.warning(f"Connection test failed: {e}, reinitializing...")
            self.is_initialized = False
            return self.initialize_mt5()
    
    def get_open_positions(self) -> List[Dict]:
        """
        Get all open positions from MT5.
        
        Returns:
            List[Dict]: List of position dictionaries with standardized keys
        """
        if not self._ensure_connection():
            logger.error("Cannot get positions: MT5 not connected")
            return []
        
        try:
            positions = mt5.positions_get()
            if positions is None:
                logger.warning("No positions found or error retrieving positions")
                return []
            
            position_list = []
            for pos in positions:
                position_data = {
                    'ticket': int(pos.ticket),
                    'symbol': str(pos.symbol),
                    'type': int(pos.type),  # 0=buy, 1=sell
                    'volume': float(pos.volume),
                    'price_open': float(pos.price_open),
                    'price_current': float(pos.price_current),
                    'profit': float(pos.profit),
                    'swap': float(pos.swap),
                    'commission': float(pos.commission),
                    'comment': str(pos.comment) if pos.comment else '',
                    'updated_at': datetime.utcnow().isoformat()
                }
                position_list.append(position_data)
            
            logger.debug(f"Retrieved {len(position_list)} open positions")
            return position_list
            
        except Exception as e:
            logger.error(f"Error retrieving positions: {e}")
            return []
    
    def get_account_info(self) -> Dict:
        """
        Get account information from MT5.
        
        Returns:
            Dict: Account information dictionary
        """
        if not self._ensure_connection():
            logger.error("Cannot get account info: MT5 not connected")
            return {}
        
        try:
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Failed to get account info")
                return {}
            
            account_data = {
                'login': int(account_info.login),
                'balance': float(account_info.balance),
                'equity': float(account_info.equity),
                'margin': float(account_info.margin),
                'free_margin': float(account_info.margin_free),
                'margin_level': float(account_info.margin_level) if account_info.margin_level else 0.0,
                'profit': float(account_info.profit),
                'currency': str(account_info.currency),
                'server': str(account_info.server),
                'company': str(account_info.company),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            logger.debug("Retrieved account information")
            return account_data
            
        except Exception as e:
            logger.error(f"Error retrieving account info: {e}")
            return {}
    
    def get_closed_deals_since(self, timestamp: datetime) -> List[Dict]:
        """
        Get closed deals since specified timestamp.
        
        Args:
            timestamp (datetime): Get deals closed after this time
            
        Returns:
            List[Dict]: List of closed deal dictionaries
        """
        if not self._ensure_connection():
            logger.error("Cannot get closed deals: MT5 not connected")
            return []
        
        try:
            # Get deals from timestamp to now
            deals = mt5.history_deals_get(timestamp, datetime.utcnow())
            if deals is None:
                logger.debug("No deals found in specified time range")
                return []
            
            closed_deals = []
            for deal in deals:
                # Filter for position close deals (entry = DEAL_ENTRY_OUT)
                if deal.entry == 1:  # DEAL_ENTRY_OUT = 1
                    deal_data = {
                        'ticket': int(deal.position_id),  # Position ticket
                        'deal_ticket': int(deal.ticket),  # Deal ticket
                        'action': 'CLOSE',
                        'symbol': str(deal.symbol),
                        'type': int(deal.type),  # 0=buy, 1=sell
                        'volume': float(deal.volume),
                        'price': float(deal.price),
                        'profit': float(deal.profit),
                        'swap': float(deal.swap),
                        'commission': float(deal.commission),
                        'comment': str(deal.comment) if deal.comment else '',
                        'timestamp': datetime.fromtimestamp(deal.time).isoformat()
                    }
                    closed_deals.append(deal_data)
            
            logger.debug(f"Retrieved {len(closed_deals)} closed deals since {timestamp}")
            return closed_deals
            
        except Exception as e:
            logger.error(f"Error retrieving closed deals: {e}")
            return []
    
    def get_deal_by_position_ticket(self, position_ticket: int) -> Optional[Dict]:
        """
        Get the closing deal for a specific position ticket.
        Useful for getting close information when position disappears.
        
        Args:
            position_ticket (int): The position ticket to find closing deal for
            
        Returns:
            Optional[Dict]: Deal data if found, None otherwise
        """
        if not self._ensure_connection():
            logger.error("Cannot get deal: MT5 not connected")
            return None
        
        try:
            # Look for deals in the last 24 hours
            since = datetime.utcnow() - timedelta(days=1)
            deals = mt5.history_deals_get(since, datetime.utcnow())
            
            if deals is None:
                return None
            
            # Find the closing deal for this position
            for deal in deals:
                if deal.position_id == position_ticket and deal.entry == 1:  # DEAL_ENTRY_OUT
                    deal_data = {
                        'ticket': int(deal.position_id),
                        'deal_ticket': int(deal.ticket),
                        'action': 'CLOSE',
                        'symbol': str(deal.symbol),
                        'type': int(deal.type),
                        'volume': float(deal.volume),
                        'price': float(deal.price),
                        'profit': float(deal.profit),
                        'swap': float(deal.swap),
                        'commission': float(deal.commission),
                        'comment': str(deal.comment) if deal.comment else '',
                        'timestamp': datetime.fromtimestamp(deal.time).isoformat()
                    }
                    logger.debug(f"Found closing deal for position {position_ticket}")
                    return deal_data
            
            logger.debug(f"No closing deal found for position {position_ticket}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving deal for position {position_ticket}: {e}")
            return None
    
    def shutdown(self):
        """Shutdown MT5 connection."""
        try:
            mt5.shutdown()
            self.is_initialized = False
            logger.info("MT5 connection shutdown")
        except Exception as e:
            logger.error(f"Error during MT5 shutdown: {e}")


# Global instance for easy import
mt5_client = MT5Client()


# Convenience functions for backward compatibility
def initialize_mt5() -> bool:
    """Initialize MT5 connection."""
    return mt5_client.initialize_mt5()


def get_open_positions() -> List[Dict]:
    """Get all open positions."""
    return mt5_client.get_open_positions()


def get_account_info() -> Dict:
    """Get account information."""
    return mt5_client.get_account_info()


def get_closed_deals_since(timestamp: datetime) -> List[Dict]:
    """Get closed deals since timestamp."""
    return mt5_client.get_closed_deals_since(timestamp)


def get_deal_by_position_ticket(position_ticket: int) -> Optional[Dict]:
    """Get closing deal for position ticket."""
    return mt5_client.get_deal_by_position_ticket(position_ticket)