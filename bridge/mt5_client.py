import MetaTrader5 as mt5
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class MT5Client:
    def __init__(self):
        self.initialized = False
    
    def initialize(self) -> bool:
        """Initialize connection to MT5 terminal"""
        try:
            # Initialize MT5 connection
            if not mt5.initialize():
                error = mt5.last_error()
                logger.error(f"Failed to initialize MT5: {error}")
                return False
            
            self.initialized = True
            logger.info("MT5 initialized successfully")
            
            # Log terminal info
            terminal_info = mt5.terminal_info()
            if terminal_info:
                logger.info(f"MT5 Terminal: {terminal_info.name} {terminal_info.build}")
            
            # Log account info
            account_info = mt5.account_info()
            if account_info:
                logger.info(f"Account: {account_info.login} ({account_info.server})")
            
            return True
            
        except Exception as e:
            logger.error(f"Exception during MT5 initialization: {e}")
            return False
    
    def shutdown(self):
        """Shutdown MT5 connection"""
        if self.initialized:
            mt5.shutdown()
            self.initialized = False
            logger.info("MT5 shutdown complete")
    
    def get_positions(self) -> List[Dict]:
        """Get current open positions"""
        if not self.initialized:
            logger.warning("MT5 not initialized")
            return []
        
        try:
            positions = mt5.positions_get()
            if positions is None:
                return []
            
            position_list = []
            for pos in positions:
                position_dict = {
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'type': pos.type,
                    'volume': pos.volume,
                    'price_open': pos.price_open,
                    'price_current': pos.price_current,
                    'profit': pos.profit,
                    'time_create': datetime.fromtimestamp(pos.time, tz=timezone.utc),
                    'time_update': datetime.fromtimestamp(pos.time_update, tz=timezone.utc),
                    'comment': pos.comment
                }
                position_list.append(position_dict)
            
            return position_list
            
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def get_deals_history(self, from_date: Optional[datetime] = None) -> List[Dict]:
        """Get trade history since specified date"""
        if not self.initialized:
            logger.warning("MT5 not initialized")
            return []
        
        try:
            # If no from_date provided, get deals from today
            if from_date is None:
                from_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Convert to timestamp
            from_timestamp = int(from_date.timestamp())
            to_timestamp = int(datetime.now(timezone.utc).timestamp())
            
            deals = mt5.history_deals_get(from_timestamp, to_timestamp)
            if deals is None:
                return []
            
            deal_list = []
            for deal in deals:
                deal_dict = {
                    'ticket': deal.ticket,
                    'order': deal.order,
                    'position_id': deal.position_id,
                    'symbol': deal.symbol,
                    'type': deal.type,
                    'entry': deal.entry,
                    'volume': deal.volume,
                    'price': deal.price,
                    'profit': deal.profit,
                    'swap': deal.swap,
                    'commission': deal.commission,
                    'time': datetime.fromtimestamp(deal.time, tz=timezone.utc),
                    'comment': deal.comment
                }
                deal_list.append(deal_dict)
            
            return deal_list
            
        except Exception as e:
            logger.error(f"Error getting deals history: {e}")
            return []