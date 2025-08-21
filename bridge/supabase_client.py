#!/usr/bin/env python3
"""
Supabase Client - Handles Supabase database operations
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL', '')
        self.service_role_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
        self.client: Optional[Client] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Supabase client"""
        try:
            if not self.url or not self.service_role_key:
                raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
            
            self.client = create_client(self.url, self.service_role_key)
            logger.info("Supabase client initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self.client = None
    
    def test_connection(self) -> bool:
        """Test Supabase connection"""
        if not self.client:
            logger.error("Supabase client not initialized")
            return False
        
        try:
            # Try to perform a simple query to test connection
            response = self.client.table('positions').select('count').execute()
            logger.info("Supabase connection test successful")
            return True
            
        except Exception as e:
            logger.error(f"Supabase connection test failed: {e}")
            return False
    
    def upsert_positions(self, positions: List[Dict]) -> bool:
        """Upsert positions to Supabase (update if exists, insert if new)"""
        if not self.client or not positions:
            return False
        
        try:
            # Prepare position data for upsert
            position_data = []
            for pos in positions:
                data = {
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
                position_data.append(data)
            
            # Upsert positions (conflict resolution on ticket)
            response = self.client.table('positions').upsert(
                position_data,
                on_conflict='ticket'
            ).execute()
            
            logger.debug(f"Upserted {len(position_data)} positions")
            return True
            
        except Exception as e:
            logger.error(f"Error upserting positions: {e}")
            return False
    
    def append_trade(self, trade_data: Dict) -> bool:
        """Append a trade record (open or close event)"""
        if not self.client:
            return False
        
        try:
            # Check for duplicate trade to avoid reprocessing
            existing = self.client.table('trades').select('id').eq(
                'ticket', trade_data['ticket']
            ).eq(
                'action', trade_data['action']
            ).eq(
                'timestamp', trade_data['timestamp']
            ).execute()
            
            if existing.data:
                logger.debug(f"Trade already exists: {trade_data['ticket']} {trade_data['action']}")
                return True
            
            # Insert new trade record
            response = self.client.table('trades').insert(trade_data).execute()
            logger.debug(f"Inserted trade: {trade_data['ticket']} {trade_data['action']}")
            return True
            
        except Exception as e:
            logger.error(f"Error appending trade: {e}")
            return False
    
    def send_heartbeat(self, heartbeat_data: Dict) -> bool:
        """Send heartbeat to indicate bridge is alive"""
        if not self.client:
            return False
        
        try:
            # Create bridge_status table entry if it doesn't exist
            # This is a simple heartbeat mechanism
            response = self.client.table('bridge_status').upsert(
                heartbeat_data,
                on_conflict='id'
            ).execute()
            
            logger.debug("Heartbeat sent")
            return True
            
        except Exception as e:
            # Don't log heartbeat errors as errors since they're not critical
            logger.debug(f"Heartbeat failed: {e}")
            return False
    
    def get_last_close_check(self) -> Optional[datetime]:
        """Get the last timestamp we checked for closes (for optimization)"""
        if not self.client:
            return None
        
        try:
            response = self.client.table('bridge_status').select('last_close_check').eq('id', 1).execute()
            
            if response.data and response.data[0].get('last_close_check'):
                return datetime.fromisoformat(response.data[0]['last_close_check'])
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting last close check: {e}")
            return None
    
    def update_last_close_check(self, timestamp: datetime) -> bool:
        """Update the last close check timestamp"""
        if not self.client:
            return False
        
        try:
            response = self.client.table('bridge_status').upsert({
                'id': 1,
                'last_close_check': timestamp.isoformat()
            }, on_conflict='id').execute()
            
            return True
            
        except Exception as e:
            logger.debug(f"Error updating last close check: {e}")
            return False