#!/usr/bin/env python3
"""
Mock MetaTrader5 module for testing purposes on Linux systems
This simulates the basic MT5 API for development and testing
"""

import time
import random
from datetime import datetime
from typing import Optional, List, Dict, Any

# Mock constants
DEAL_ENTRY_OUT = 1

class MockPosition:
    def __init__(self, ticket: int, symbol: str, type_: int):
        self.ticket = ticket
        self.symbol = symbol
        self.type = type_  # 0=buy, 1=sell
        self.volume = round(random.uniform(0.01, 1.0), 2)
        self.price_open = round(random.uniform(1.0, 2.0), 5)
        self.price_current = round(self.price_open + random.uniform(-0.01, 0.01), 5)
        self.profit = round((self.price_current - self.price_open) * self.volume * 100, 2)
        self.swap = round(random.uniform(-5.0, 5.0), 2)
        self.commission = round(random.uniform(-2.0, 0.0), 2)
        self.comment = f"Mock position {ticket}"
        self.time = int(time.time())
        self.time_update = int(time.time())

class MockDeal:
    def __init__(self, ticket: int, position_id: int, symbol: str):
        self.ticket = ticket
        self.position_id = position_id
        self.symbol = symbol
        self.type = random.choice([0, 1])
        self.entry = DEAL_ENTRY_OUT
        self.volume = round(random.uniform(0.01, 1.0), 2)
        self.price = round(random.uniform(1.0, 2.0), 5)
        self.profit = round(random.uniform(-50.0, 50.0), 2)
        self.swap = round(random.uniform(-5.0, 5.0), 2)
        self.commission = round(random.uniform(-2.0, 0.0), 2)
        self.comment = f"Mock deal {ticket}"
        self.time = int(time.time())

class MockAccountInfo:
    def __init__(self):
        self.login = 12345678
        self.server = "MockServer-Demo"
        self.name = "Mock Account"
        self.company = "Mock Broker"
        self.currency = "USD"
        self.balance = 10000.0
        self.equity = 10500.0
        self.margin = 500.0
        self.margin_free = 10000.0
        self.margin_level = 2100.0
        self.profit = 500.0

# Global mock state
_initialized = False
_logged_in = False
_mock_positions = {}
_position_counter = 1000

def initialize() -> bool:
    """Mock MT5 initialize"""
    global _initialized
    print("Mock MT5: initialize() called")
    _initialized = True
    return True

def login(login: int, password: str, server: str) -> bool:
    """Mock MT5 login"""
    global _logged_in
    print(f"Mock MT5: login({login}, '***', '{server}') called")
    if _initialized:
        _logged_in = True
        return True
    return False

def shutdown():
    """Mock MT5 shutdown"""
    global _initialized, _logged_in
    print("Mock MT5: shutdown() called")
    _initialized = False
    _logged_in = False

def last_error():
    """Mock MT5 last_error"""
    return (0, "No error")

def account_info() -> Optional[MockAccountInfo]:
    """Mock MT5 account_info"""
    if _logged_in:
        return MockAccountInfo()
    return None

def positions_get() -> Optional[List[MockPosition]]:
    """Mock MT5 positions_get"""
    if not _logged_in:
        return None
    
    # Create some mock positions
    global _mock_positions, _position_counter
    
    # Randomly add/remove positions to simulate trading
    if random.random() < 0.3:  # 30% chance to add a position
        ticket = _position_counter
        _position_counter += 1
        symbol = random.choice(["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"])
        type_ = random.choice([0, 1])
        _mock_positions[ticket] = MockPosition(ticket, symbol, type_)
    
    if _mock_positions and random.random() < 0.2:  # 20% chance to remove a position
        ticket_to_remove = random.choice(list(_mock_positions.keys()))
        del _mock_positions[ticket_to_remove]
    
    # Update existing positions
    for pos in _mock_positions.values():
        pos.price_current = round(pos.price_open + random.uniform(-0.02, 0.02), 5)
        pos.profit = round((pos.price_current - pos.price_open) * pos.volume * 100, 2)
        pos.time_update = int(time.time())
    
    return list(_mock_positions.values())

def history_deals_get(start_timestamp: int, end_timestamp: int) -> Optional[List[MockDeal]]:
    """Mock MT5 history_deals_get"""
    if not _logged_in:
        return None
    
    # Generate some mock closed deals
    deals = []
    for i in range(random.randint(0, 3)):  # 0-3 mock deals
        ticket = random.randint(2000, 9999)
        position_id = random.randint(1000, 1999)
        symbol = random.choice(["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"])
        deals.append(MockDeal(ticket, position_id, symbol))
    
    return deals

# For compatibility
def symbol_info_tick(symbol: str):
    """Mock symbol_info_tick"""
    return None