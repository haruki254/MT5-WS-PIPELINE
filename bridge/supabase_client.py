"""
Supabase client for MT5 bridge integration.
Handles position upserts, trade logging, and bridge health monitoring.
Schema-compliant version with improved error handling.
"""

import os
from datetime import datetime, timezone
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
        
        if not self.url:
            raise ValueError(
                "SUPABASE_URL environment variable is required. "
                "Set it to your Supabase project URL (e.g., https://xxx.supabase.co)"
            )
        
        if not self.key:
            raise ValueError(
                "SUPABASE_SERVICE_ROLE_KEY environment variable is required. "
                "Get it from your Supabase project settings > API > service_role key"
            )
        
        try:
            self.supabase: Client = create_client(self.url, self.key)
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise

    def _get_utc_now(self) -> str:
        """Get current UTC timestamp as ISO string."""
        return datetime.now(timezone.utc).isoformat()

    def _convert_mt5_type_to_string(self, mt5_type: int) -> str:
        """Convert MT5 position type integer to string."""
        type_map = {
            0: 'buy',
            1: 'sell'
        }
        return type_map.get(mt5_type, 'unknown')

    def upsert_positions(self, positions: List[Dict]) -> None:
        """
        Upsert positions to prevent duplicates.
        Uses ticket as primary key for conflict resolution.
        
        Args:
            positions: List of position dictionaries with MT5 position data
        """
        if not positions:
            logger.debug("No positions to upsert")
            return
        
        try:
            # Transform positions to match database schema
            formatted_positions = []
            for pos in positions:
                # Validate required fields
                required_fields = ['ticket', 'symbol', 'type', 'volume', 'price_open']
                for field in required_fields:
                    if field not in pos:
                        raise ValueError(f"Missing required field '{field}' in position data")
                
                formatted_pos = {
                    'ticket': int(pos['ticket']),
                    'symbol': str(pos['symbol']),
                    'type': int(pos['type']),  # Keep as integer to match schema
                    'volume': float(pos['volume']),
                    'price_open': float(pos['price_open']),
                    'price_current': float(pos.get('price_current', pos['price_open'])),
                    'profit': float(pos.get('profit', 0.0)),
                    'swap': float(pos.get('swap', 0.0)),
                    'commission': float(pos.get('commission', 0.0)),
                    'comment': str(pos.get('comment', '')),
                    'updated_at': self._get_utc_now()
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
        Includes duplicate prevention check based on ticket + action combination.
        
        Args:
            trade_data: Dictionary containing trade information
        """
        try:
            # Validate required fields
            required_fields = ['ticket', 'symbol', 'type', 'action', 'volume', 'price']
            for field in required_fields:
                if field not in trade_data:
                    raise ValueError(f"Missing required field '{field}' in trade data")
            
            # Validate action
            if trade_data['action'] not in ['OPEN', 'CLOSE']:
                raise ValueError(f"Invalid action '{trade_data['action']}'. Must be 'OPEN' or 'CLOSE'")
            
            ticket = int(trade_data['ticket'])
            action = str(trade_data['action'])
            
            # Check for existing trade to prevent duplicates
            # We check based on ticket + action, not timestamp
            existing = self.supabase.table('trades').select('id').eq(
                'ticket', ticket
            ).eq(
                'action', action
            ).execute()
            
            if existing.data:
                logger.warning(f"Trade already exists: ticket={ticket}, action={action}")
                return
            
            # Format trade data to match schema
            formatted_trade = {
                'ticket': ticket,
                'symbol': str(trade_data['symbol']),
                'type': self._convert_mt5_type_to_string(int(trade_data['type'])),  # Convert to string
                'action': action,
                'volume': float(trade_data['volume']),
                'price': float(trade_data['price']),
                'profit': float(trade_data.get('profit', 0.0)) if trade_data.get('profit') is not None else 0.0,
                'swap': float(trade_data.get('swap', 0.0)),
                'commission': float(trade_data.get('commission', 0.0)),
                'comment': str(trade_data.get('comment', ''))
                # created_at will be set automatically by database
            }
            
            result = self.supabase.table('trades').insert(formatted_trade).execute()
            logger.info(f"Trade recorded: {action} ticket={ticket} symbol={trade_data['symbol']}")
            
        except Exception as e:
            logger.error(f"Error appending trade: {e}")
            raise

    def get_last_close_check(self) -> datetime:
        """
        Get the timestamp of the last close detection check.
        Used to avoid reprocessing closed trades.
        
        Returns:
            datetime: Last close check timestamp in UTC
        """
        try:
            result = self.supabase.table('bridge_status').select(
                'last_close_check'
            ).eq('id', 1).execute()
            
            if result.data and result.data[0].get('last_close_check'):
                timestamp_str = result.data[0]['last_close_check']
                # Handle both Z and +00:00 timezone formats
                if timestamp_str.endswith('Z'):
                    timestamp_str = timestamp_str.replace('Z', '+00:00')
                return datetime.fromisoformat(timestamp_str)
            else:
                # Return start of today if no record exists
                default_time = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                logger.info("No last_close_check found, returning start of today")
                return default_time
                
        except Exception as e:
            logger.error(f"Error getting last close check: {e}")
            # Return a safe default - start of today
            return datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

    def update_last_close_check(self, timestamp: datetime) -> None:
        """
        Update the last close check timestamp.
        
        Args:
            timestamp: The timestamp to set as last close check
        """
        try:
            # Ensure timestamp is timezone-aware
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            
            self.supabase.table('bridge_status').upsert({
                'id': 1,
                'last_close_check': timestamp.isoformat(),
                'updated_at': self._get_utc_now()
            }, on_conflict='id').execute()
            
            logger.debug(f"Updated last close check to {timestamp}")
            
        except Exception as e:
            logger.error(f"Error updating last close check: {e}")
            raise

    def send_heartbeat(self, status: str = 'active') -> None:
        """
        Send heartbeat to indicate bridge is healthy and running.
        Creates or updates bridge_status record.
        
        Args:
            status: Bridge status ('active', 'error', 'stopped', etc.)
        """
        try:
            heartbeat_data = {
                'id': 1,
                'status': str(status),
                'updated_at': self._get_utc_now()
            }
            
            result = self.supabase.table('bridge_status').upsert(
                heartbeat_data,
                on_conflict='id'
            ).execute()
            
            logger.debug(f"Heartbeat sent successfully with status: {status}")
            
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
            # Don't raise - heartbeat failures shouldn't stop the main loop

    def cleanup_old_positions(self, current_tickets: List[int]) -> None:
        """
        Remove positions that are no longer open.
        Called when we detect closed positions.
        
        Args:
            current_tickets: List of ticket numbers that are currently open
        """
        if not current_tickets:
            # If no positions are open, clear the table
            try:
                result = self.supabase.table('positions').delete().neq('ticket', 0).execute()
                deleted_count = len(result.data) if result.data else 0
                logger.info(f"Cleared all positions ({deleted_count} records) - no open trades")
            except Exception as e:
                logger.error(f"Error clearing all positions: {e}")
                raise
            return
        
        try:
            # Delete positions not in current_tickets list
            result = self.supabase.table('positions').delete().not_.in_(
                'ticket', current_tickets
            ).execute()
            
            deleted_count = len(result.data) if result.data else 0
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} closed positions")
            else:
                logger.debug("No closed positions to clean up")
                
        except Exception as e:
            logger.error(f"Error cleaning up old positions: {e}")
            raise

    def get_open_position_tickets(self) -> List[int]:
        """
        Get list of currently tracked open position tickets.
        Used for close detection logic.
        
        Returns:
            List[int]: List of open position ticket numbers
        """
        try:
            result = self.supabase.table('positions').select('ticket').execute()
            tickets = [row['ticket'] for row in result.data] if result.data else []
            logger.debug(f"Found {len(tickets)} open position tickets")
            return tickets
            
        except Exception as e:
            logger.error(f"Error getting open position tickets: {e}")
            return []

    def get_bridge_status(self) -> Dict:
        """
        Get current bridge status information.
        
        Returns:
            Dict: Bridge status information
        """
        try:
            result = self.supabase.table('bridge_status').select('*').eq('id', 1).execute()
            
            if result.data:
                return result.data[0]
            else:
                return {
                    'id': 1,
                    'last_close_check': None,
                    'status': 'unknown',
                    'updated_at': None
                }
                
        except Exception as e:
            logger.error(f"Error getting bridge status: {e}")
            return {
                'id': 1,
                'last_close_check': None,
                'status': 'error',
                'updated_at': None
            }

    def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """
        Get recent trades from the database.
        
        Args:
            limit: Maximum number of trades to return
            
        Returns:
            List[Dict]: Recent trades ordered by created_at desc
        """
        try:
            result = self.supabase.table('trades').select('*').order(
                'created_at', desc=True
            ).limit(limit).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []

    def health_check(self) -> bool:
        """
        Perform a health check on the Supabase connection.
        
        Returns:
            bool: True if connection is healthy, False otherwise
        """
        try:
            # Try a simple query to test connection
            result = self.supabase.table('bridge_status').select('id').limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


# Module-level client instance - lazy initialization
_client: Optional[SupabaseClient] = None

def get_client() -> SupabaseClient:
    """Get or create the Supabase client instance."""
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client

# Convenience functions for backward compatibility
def upsert_positions(positions: List[Dict]) -> None:
    """Upsert positions to Supabase."""
    get_client().upsert_positions(positions)

def append_trade(trade_data: Dict) -> None:
    """Append trade event to Supabase."""
    get_client().append_trade(trade_data)

def get_last_close_check() -> datetime:
    """Get last close check timestamp."""
    return get_client().get_last_close_check()

def update_last_close_check(timestamp: datetime) -> None:
    """Update last close check timestamp."""
    get_client().update_last_close_check(timestamp)

def send_heartbeat(status: str = 'active') -> None:
    """Send bridge heartbeat."""
    get_client().send_heartbeat(status)

def cleanup_old_positions(current_tickets: List[int]) -> None:
    """Clean up old positions."""
    get_client().cleanup_old_positions(current_tickets)

def get_open_position_tickets() -> List[int]:
    """Get open position tickets."""
    return get_client().get_open_position_tickets()

def health_check() -> bool:
    """Perform health check."""
    return get_client().health_check()