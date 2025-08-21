#!/usr/bin/env python3
"""
MT5 Client for MetaTrader 5 Integration
Handles connection, position retrieval, and historical data access
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

class MT5Client:
    def __init__(self):
        self.login = int(os.getenv('MT5_LOGIN', 0))
        self.password = os.getenv('MT5_PASSWORD', '')
        self.server = os.getenv('MT5_SERVER', '')
        self.is_initialized = False
        
    def initialize_mt5(self) -> bool:
        """Initialize connection to MT5 terminal"""
        try:
            # Initialize MT5 connection
            if not mt5.initialize():
                error_code = mt5.last_error()
                logger.error(f"MT5 initialize failed: {error_code}")
                return False
            
            # Login with credentials
            if self.login and self.password and self.server:
                login_result = mt5.login(
                    login=self.login,
                    password=self.password,
                    server=self.server
                )
                
                if not login_result:
                    error_code = mt5.last_error()
                    logger.error(f"MT5 login failed: {error_code}")
                    mt5.shutdown()
                    return False
                    
                logger.info(f"MT5 connected to account {self.login} on {self.server}")
            else:
                logger.warning("MT5 credentials not provided, using current terminal session")
            
            # Verify connection
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Failed to get account info")
                mt5.shutdown()
                return False
                
            logger.info(f"MT5 account: {account_info.login}, balance: {account_info.balance}")
            self.is_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"MT5 initialization error: {e}")
            return False
    
    def get_open_positions(self) -> List[Dict]:
        """
        Get all currently open positions from MT5
        Returns list of position dictionaries
        """
        if not self.is_initialized:
            logger.warning("MT5 not initialized, attempting to reconnect...")
            if not self.initialize_mt5():
                return []
        
        try:
            positions = mt5.positions_get()
            if positions is None:
                logger.warning("No positions found or error getting positions")
                return []
            
            position_list = []
            for pos in positions:
                position_data = {
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'type': pos.type,  # 0=buy, 1=sell
                    'volume': float(pos.volume),
                    'price_open': float(pos.price_open),
                    'price_current': float(pos.price_current),
                    'profit': float(pos.profit),
                    'swap': float(pos.swap),
                    'commission': float(pos.commission),
                    'comment': pos.comment or '',
                    'time': pos.time,
                    'time_update': pos.time_update
                }
                position_list.append(position_data)
            
            logger.debug(f"Retrieved {len(position_list)} open positions")
            return position_list
            
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            self.is_initialized = False  # Force reconnect on next call
            return []
    
    def get_account_info(self) -> Dict:
        """Get MT5 account information"""
        if not self.is_initialized:
            if not self.initialize_mt5():
                return {}
        
        try:
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Failed to get account info")
                return {}
            
            return {
                'login': account_info.login,
                'trade_mode': account_info.trade_mode,
                'balance': float(account_info.balance),
                'equity': float(account_info.equity),
                'margin': float(account_info.margin),
                'margin_free': float(account_info.margin_free),
                'margin_level': float(account_info.margin_level),
                'profit': float(account_info.profit),
                'currency': account_info.currency,
                'server': account_info.server,
                'name': account_info.name
            }
            
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {}
    
    def get_closed_deals_since(self, since_time: datetime) -> List[Dict]:
        """
        Get closed deals (trades) since specified time
        Used for detecting position closes
        """
        if not self.is_initialized:
            if not self.initialize_mt5():
                return []
        
        try:
            # Convert datetime to MT5 format
            from_date = since_time
            to_date = datetime.now()
            
            # Get deals history
            deals = mt5.history_deals_get(from_date, to_date)
            if deals is None:
                logger.debug("No deals found in history")
                return []
            
            deal_list = []
            for deal in deals:
                # Only include position close deals (deal_type = DEAL_TYPE_SELL for buy positions, etc.)
                if deal.entry == mt5.DEAL_ENTRY_OUT:  # Position close
                    deal_data = {
                        'ticket': deal.ticket,
                        'position_id': deal.position_id,
                        'symbol': deal.symbol,
                        'type': deal.type,
                        'volume': float(deal.volume),
                        'price': float(deal.price),
                        'profit': float(deal.profit),
                        'swap': float(deal.swap),
                        'commission': float(deal.commission),
                        'comment': deal.comment or '',
                        'time': deal.time,
                        'entry': deal.entry
                    }
                    deal_list.append(deal_data)
            
            logger.debug(f"Retrieved {len(deal_list)} closed deals since {since_time}")
            return deal_list
            
        except Exception as e:
            logger.error(f"Error getting closed deals: {e}")
            return []
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get information about a trading symbol"""
        if not self.is_initialized:
            if not self.initialize_mt5():
                return None
        
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            return {
                'name': symbol_info.name,
                'digits': symbol_info.digits,
                'spread': symbol_info.spread,
                'point': symbol_info.point,
                'bid': float(symbol_info.bid),
                'ask': float(symbol_info.ask),
                'volume_min': float(symbol_info.volume_min),
                'volume_max': float(symbol_info.volume_max),
                'volume_step': float(symbol_info.volume_step),
                'trade_mode': symbol_info.trade_mode
            }
            
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol}: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test if MT5 connection is working"""
        try:
            if not self.is_initialized:
                return self.initialize_mt5()
            
            # Try to get account info as connection test
            account_info = mt5.account_info()
            return account_info is not None
            
        except Exception as e:
            logger.error(f"MT5 connection test failed: {e}")
            self.is_initialized = False
            return False
    
    def shutdown(self) -> None:
        """Shutdown MT5 connection"""
        try:
            if self.is_initialized:
                mt5.shutdown()
                self.is_initialized = False
                logger.info("MT5 connection closed")
        except Exception as e:
            logger.error(f"Error during MT5 shutdown: {e}")
    
    def __del__(self):
        """Cleanup on object destruction"""
        self.shutdown()