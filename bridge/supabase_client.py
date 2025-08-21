#!/usr/bin/env python3
"""
Supabase Client for MT5 Bridge
Handles database operations, position upserts, trade logging, and heartbeat
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        self.client: Optional[Client] = None
        
        if not self.url or not self.service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize Supabase client with service role key"""
        try:
            self.client = create_client(self.url, self.service_key)
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    def test_connection(self) -> bool:
        """Test Supabase connection"""
        try:
            if not self.client:
                self._initialize_client()
            
            # Try a simple query to test connection
            result = self.client.table('bridge_status').select('id').limit(1).execute()
            logger.info("Supabase connection test successful")
            return True
            
        except Exception as e:
            logger.error(f"Supabase connection test failed: {e}")
            return False
    
    def upsert_positions(self, positions: List[Dict]) -> bool:
        """
        Upsert positions to the database
        Uses ticket as primary key for upsert operation
        """
        if not positions:
            return True
            
        try:
            # Prepare position data for upsert
            position_records = []
            for pos in positions:
                record = {
                    'ticket': pos['ticket'],
                    'symbol': pos['symbol'],
                    'type': pos['type'],
                    'volume': pos['volume'],
                    'price_open': pos['price_open'],
                    'price_current': pos['price_current'],
                    'profit': pos['profit'],
                    'swap': pos['swap'],
                    'commission': pos['commission'],
                    'comment': pos['comment'],
                    'updated_at': datetime.now().isoformat()
                }
                position_records.append(record)
            
            # Perform upsert operation
            result = self.client.table('positions').upsert(
                position_records,
                on_conflict='ticket'
            ).execute()
            
            if result.data:
                logger.debug(f"Successfully upserted {len(result.data)} positions")
                return True
            else:
                logger.warning("Upsert returned no data")
                return False
                
        except Exception as e:
            logger.error(f"Error upserting positions: {e}")
            return False
    
    def append_trade(self, trade_data: Dict) -> bool:
        """
        Append a trade record (open or close event)
        Includes duplicate prevention using unique constraint
        """
        try:
            # Prepare trade record
            trade_record = {
                'ticket': trade_data['ticket'],
                'action': trade_data['action'],
                'symbol': trade_data['symbol'],
                'type': trade_data['type'],
                'volume': trade_data['volume'],
                'price': trade_data['price'],
                'profit': trade_data.get('profit'),
                'swap': trade_data.get('swap', 0),
                'commission': trade_data.get('commission', 0),
                'comment': trade_data.get('comment', ''),
                'timestamp': trade_data.get('timestamp', datetime.now().isoformat())
            }
            
            # Insert trade record
            result = self.client.table('trades').insert(trade_record).execute()
            
            if result.data:
                logger.debug(f"Successfully recorded {trade_data['action']} trade for ticket {trade_data['ticket']}")
                return True
            else:
                logger.warning(f"Trade insert returned no data for ticket {trade_data['ticket']}")
                return False
                
        except Exception as e:
            # Check if it's a duplicate constraint error
            if 'duplicate key value violates unique constraint' in str(e).lower():
                logger.debug(f"Trade record already exists for ticket {trade_data['ticket']}, action {trade_data['action']}")
                return True  # Consider duplicates as success
            else:
                logger.error(f"Error inserting trade: {e}")
                return False
    
    def send_heartbeat(self, heartbeat_data: Dict) -> bool:
        """
        Send heartbeat to indicate bridge is alive
        Updates the bridge_status table
        """
        try:
            # Prepare heartbeat record
            heartbeat_record = {
                'id': 1,  # Single row table
                'last_seen': heartbeat_data.get('last_seen', datetime.now().isoformat()),
                'status': heartbeat_data.get('status', 'healthy'),
                'positions_count': heartbeat_data.get('positions_count', 0),
                'error_message': heartbeat_data.get('error_message'),
                'updated_at': datetime.now().isoformat()
            }
            
            # Upsert heartbeat record
            result = self.client.table('bridge_status').upsert(
                heartbeat_record,
                on_conflict='id'
            ).execute()
            
            if result.data:
                logger.debug(f"Heartbeat sent: {heartbeat_record['status']}")
                return True
            else:
                logger.warning("Heartbeat upsert returned no data")
                return False
                
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
            return False
    
    def get_last_close_check(self) -> Optional[datetime]:
        """
        Get timestamp of last close check to avoid reprocessing
        This can be used to track the last time we checked for closes
        """
        try:
            result = self.client.table('bridge_status').select('last_seen').eq('id', 1).execute()
            
            if result.data and len(result.data) > 0:
                last_seen_str = result.data[0]['last_seen']
                return datetime.fromisoformat(last_seen_str.replace('Z', '+00:00'))
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting last close check: {e}")
            return None
    
    def get_recent_trades(self, limit: int = 100) -> List[Dict]:
        """Get recent trade records for monitoring"""
        try:
            result = self.client.table('trades').select('*').order(
                'timestamp', desc=True
            ).limit(limit).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []
    
    def get_current_positions(self) -> List[Dict]:
        """Get current positions from database"""
        try:
            result = self.client.table('positions').select('*').order(
                'updated_at', desc=True
            ).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Error getting current positions: {e}")
            return []
    
    def cleanup_old_trades(self, days_old: int = 30) -> bool:
        """
        Clean up old trade records to prevent database bloat
        Keeps trades newer than specified days
        """
        try:
            cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_date = cutoff_date - timedelta(days=days_old)
            cutoff_iso = cutoff_date.isoformat()
            
            result = self.client.table('trades').delete().lt(
                'timestamp', cutoff_iso
            ).execute()
            
            if result.data:
                logger.info(f"Cleaned up {len(result.data)} old trade records")
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up old trades: {e}")
            return False
    
    def get_position_by_ticket(self, ticket: int) -> Optional[Dict]:
        """Get specific position by ticket number"""
        try:
            result = self.client.table('positions').select('*').eq('ticket', ticket).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting position {ticket}: {e}")
            return None
    
    def delete_position(self, ticket: int) -> bool:
        """Delete position from database (used when position is closed)"""
        try:
            result = self.client.table('positions').delete().eq('ticket', ticket).execute()
            
            if result.data:
                logger.debug(f"Deleted position {ticket} from database")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting position {ticket}: {e}")
            return False
    
    def get_bridge_status(self) -> Optional[Dict]:
        """Get current bridge status"""
        try:
            result = self.client.table('bridge_status').select('*').eq('id', 1).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting bridge status: {e}")
            return None