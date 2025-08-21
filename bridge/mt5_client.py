#!/usr/bin/env python3
"""
MT5 Client - Handles MetaTrader 5 connections and data retrieval
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
        self.initialized = False
        
    def initialize_mt5(self) -> bool:
        """Initialize MT5 connection"""
        try:
            # Initialize MT5
            if not mt5.initialize():
                logger.error("MT5 initialize() failed")
                return False
            
            # Login to account
            if not mt5.login(self.login, self.password, self.server):
                error_code = mt5.last_error()
                logger.error(f"MT5 login failed: {error_code}")
                mt5.shutdown()
                return False
            
            # Get account info to verify connection
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Failed to get account info")
                mt5.shutdown()
                return False
            
            logger.info(f"MT5 initialized successfully. Account: {account_info.login}, Server: {account_info.server}")
            self.initialized = True
            return True
            
        except Exception as e:
            logger.error(f"MT5 initialization error: {e}")
            return False
    
    def get_open_positions(self) -> List[Dict]:
        """Get all currently open positions"""
        if not self.initialized:
            logger.warning("MT5 not initialized, attempting to initialize...")
            if not self.initialize_mt5():
                return []
        
        try:
            positions = mt5.positions_get()
            if positions is None:
                logger.warning("No positions found or error occurred")
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
                    'comment': pos.comment,
                    'time': pos.time,
                    'time_update': pos.time_update
                }
                position_list.append(position_data)
            
            return position_list
            
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []
    
    def get_account_info(self) -> Dict:
        """Get account information"""
        if not self.initialized:
            logger.warning("MT5 not initialized")
            return {}
        
        try:
            account_info = mt5.account_info()
            if account_info is None:
                return {}
            
            return {
                'login': account_info.login,
                'server': account_info.server,
                'name': account_info.name,
                'company': account_info.company,
                'currency': account_info.currency,
                'balance': float(account_info.balance),
                'equity': float(account_info.equity),
                'margin': float(account_info.margin),
                'margin_free': float(account_info.margin_free),
                'margin_level': float(account_info.margin_level) if account_info.margin_level else 0,
                'profit': float(account_info.profit)
            }
            
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {}
    
    def get_closed_deals_since(self, start_time: datetime) -> List[Dict]:
        """Get closed deals since the specified timestamp for close detection"""
        if not self.initialized:
            logger.warning("MT5 not initialized")
            return []
        
        try:
            # Convert datetime to timestamp
            start_timestamp = int(start_time.timestamp())
            end_timestamp = int(datetime.now().timestamp())
            
            # Get deals from history
            deals = mt5.history_deals_get(start_timestamp, end_timestamp)
            if deals is None:
                logger.warning("No deals found in history")
                return []
            
            deal_list = []
            for deal in deals:
                # Only process OUT deals (position closes)
                if deal.entry == mt5.DEAL_ENTRY_OUT:
                    deal_data = {
                        'ticket': deal.ticket,
                        'position_id': deal.position_id,  # This links to the position ticket
                        'symbol': deal.symbol,
                        'type': deal.type,
                        'volume': float(deal.volume),
                        'price': float(deal.price),
                        'profit': float(deal.profit),
                        'swap': float(deal.swap),
                        'commission': float(deal.commission),
                        'comment': deal.comment,
                        'time': deal.time
                    }
                    deal_list.append(deal_data)
            
            return deal_list
            
        except Exception as e:
            logger.error(f"Error getting closed deals: {e}")
            return []
    
    def shutdown(self):
        """Shutdown MT5 connection"""
        try:
            if self.initialized:
                mt5.shutdown()
                self.initialized = False
                logger.info("MT5 connection shut down")
        except Exception as e:
            logger.warning(f"Error during MT5 shutdown: {e}")