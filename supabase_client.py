"""
Supabase client for MT5 bridge integration.
Handles position upserts, trade logging, and bridge health monitoring.
"""

import os
from datetime import datetime
from typing import List, Dict, Optional
from supabase import create_client, Client
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        """Initialize Supabase client with service role key for full access."""
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment")
        
        self.supabase: Client = create_client(self.url, self.key)
        logger.info("Supabase client initialized")

    def upsert_positions(self, positions: List[Dict]) -> None:
        """
        Upsert positions to prevent duplicates.
        Uses ticket as primary key for conflict resolution.
        """
        if not positions:
            return
        
        try:
            # Transform positions to match database schema
            formatted_positions = []
            for pos in positions:
                formatted_pos = {
                    'ticket': pos['ticket'],
                    'symbol': pos['symbol'],
                    'type': pos['type'],
                    'volume': float(pos['volume']),
                    'price_open': float(pos['price_open']),
                    'price_current': float(pos.get('price_current', pos['price_open'])),
                    'profit': float(pos.get('profit', 0)),
                    'swap': float(pos.get('swap', 0)),
                    'commission': float(pos.get('commission', 0)),
                    'comment': pos.get('comment', ''),
                    'updated_at': datetime.utcnow().isoformat()
                }
                formatted_positions.append(formatted_pos)
            
            # Upsert with conflict resolution on ticket
            result = self.supabase.table('positions').upsert(
                formatted_positions,
                on_conflict='ticket'
            ).execute()
            
            logger.info(f"Successfully upserted {len(formatted_positions)} positions")
            
        except Exception as e:
            logger.error(f"Error upserting positions: {e}")
            raise

    def append_trade(self, trade_data: Dict) -> None:
        """
        Append trade event (OPEN/CLOSE) to trades table.
        Includes duplicate prevention check.
        """
        try:
            # Check for existing trade to prevent duplicates
            existing = self.supabase.table('trades').select('id').eq(
                'ticket', trade_data['ticket']
            ).eq(
                'action', trade_data['action']
            ).eq(
                'timestamp', trade_data.get('timestamp', datetime.utcnow().isoformat())
            ).execute()
            
            if existing.data:
                logger.warning(f"Trade already exists: ticket={trade_data['ticket']}, action={trade_data['action']}")
                return
            
            # Format trade data
            formatted_trade = {
                'ticket': trade_data['ticket'],
                'action': trade_data['action'],  # 'OPEN' or 'CLOSE'
                'symbol': trade_data['symbol'],
                'type': trade_data['type'],
                'volume': float(trade_data['volume']),
                'price': float(trade_data['price']),
                'profit': float(trade_data.get('profit', 0)) if trade_data.get('profit') is not None else None,
                'swap': float(trade_data.get('swap', 0)),
                'commission': float(trade_data.get('commission', 0)),
                'comment': trade_data.get('comment', ''),
                'timestamp': trade_data.get('timestamp', datetime.utcnow().isoformat())
            }
            
            result = self.supabase.table('trades').insert(formatted_trade).execute()
            logger.info(f"Trade recorded: {trade_data['action']} ticket={trade_data['ticket']}")
            
        except Exception as e:
            logger.error(f"Error appending trade: {e}")
            raise

    def get_last_close_check(self) -> datetime:
        """
        Get the timestamp of the last close detection check.
        Used to avoid reprocessing closed trades.
        """
        try:
            result = self.supabase.table('bridge_status').select(
                'last_close_check'
            ).eq('id', 1).execute()
            
            if result.data and result.data[0].get('last_close_check'):
                return datetime.fromisoformat(result.data[0]['last_close_check'].replace('Z', '+00:00'))
            else:
                # Return a default timestamp if no record exists
                return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                
        except Exception as e:
            logger.error(f"Error getting last close check: {e}")
            # Return a safe default
            return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    def update_last_close_check(self, timestamp: datetime) -> None:
        """Update the last close check timestamp."""
        try:
            self.supabase.table('bridge_status').upsert({
                'id': 1,
                'last_close_check': timestamp.isoformat(),
                'last_seen': datetime.utcnow().isoformat()
            }, on_conflict='id').execute()
            
        except Exception as e:
            logger.error(f"Error updating last close check: {e}")

    def send_heartbeat(self) -> None:
        """
        Send heartbeat to indicate bridge is healthy and running.
        Creates or updates bridge_status record.
        """
        try:
            heartbeat_data = {
                'id': 1,
                'last_seen': datetime.utcnow().isoformat(),
                'status': 'healthy'
            }
            
            result = self.supabase.table('bridge_status').upsert(
                heartbeat_data,
                on_conflict='id'
            ).execute()
            
            logger.debug("Heartbeat sent successfully")
            
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
            # Don't raise - heartbeat failures shouldn't stop the main loop

    def cleanup_old_positions(self, current_tickets: List[int]) -> None:
        """
        Remove positions that are no longer open.
        Called when we detect closed positions.
        """
        if not current_tickets:
            # If no positions are open, clear the table
            try:
                result = self.supabase.table('positions').delete().neq('ticket', 0).execute()
                logger.info("Cleared all positions - no open trades")
            except Exception as e:
                logger.error(f"Error clearing positions: {e}")
            return
        
        try:
            # Delete positions not in current_tickets list
            result = self.supabase.table('positions').delete().not_.in_(
                'ticket', current_tickets
            ).execute()
            
            if result.data:
                logger.info(f"Cleaned up {len(result.data)} closed positions")
                
        except Exception as e:
            logger.error(f"Error cleaning up old positions: {e}")

    def get_open_position_tickets(self) -> List[int]:
        """
        Get list of currently tracked open position tickets.
        Used for close detection logic.
        """
        try:
            result = self.supabase.table('positions').select('ticket').execute()
            return [row['ticket'] for row in result.data] if result.data else []
            
        except Exception as e:
            logger.error(f"Error getting open position tickets: {e}")
            return []

# Global instance
supabase_client = SupabaseClient()

# Convenience functions for backward compatibility
def upsert_positions(positions: List[Dict]) -> None:
    """Upsert positions to Supabase."""
    supabase_client.upsert_positions(positions)

def append_trade(trade_data: Dict) -> None:
    """Append trade event to Supabase."""
    supabase_client.append_trade(trade_data)

def get_last_close_check() -> datetime:
    """Get last close check timestamp."""
    return supabase_client.get_last_close_check()

def send_heartbeat() -> None:
    """Send bridge heartbeat."""
    supabase_client.send_heartbeat()