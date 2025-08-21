# MT5 to React via Supabase: Production Implementation Plan

## Quick Setup with Your Credentials

**Supabase Project:** `hmehzemjfgahqyoljdps`  
**URL:** `https://hmehzemjfgahqyoljdps.supabase.co`

1. Run the SQL schema (Section 2) in your Supabase SQL Editor
2. Create bridge `.env` with your MT5 credentials (Section 3)
3. Set frontend `.env.local` with anon key
4. Follow the numbered sections below

## 1. Prerequisites

```bash
# Bridge (Windows/MT5 machine)
pip install MetaTrader5 supabase python-dotenv

# Frontend
npm install @supabase/supabase-js @types/node
```

## 2. Supabase Schema & Realtime

```sql
-- Enable realtime on public schema
ALTER PUBLICATION supabase_realtime ADD TABLE public.positions;
ALTER PUBLICATION supabase_realtime ADD TABLE public.trades;

-- Positions table (upserted by ticket)
CREATE TABLE positions (
  ticket BIGINT PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  type INTEGER NOT NULL, -- 0=buy, 1=sell
  volume DECIMAL(10,2) NOT NULL,
  price_open DECIMAL(10,5) NOT NULL,
  price_current DECIMAL(10,5),
  profit DECIMAL(10,2),
  swap DECIMAL(10,2),
  commission DECIMAL(10,2),
  comment TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trades table (append-only for open/close events)
CREATE TABLE trades (
  id BIGSERIAL PRIMARY KEY,
  ticket BIGINT NOT NULL,
  action VARCHAR(10) NOT NULL, -- 'OPEN' or 'CLOSE'
  symbol VARCHAR(20) NOT NULL,
  type INTEGER NOT NULL,
  volume DECIMAL(10,2) NOT NULL,
  price DECIMAL(10,5) NOT NULL,
  profit DECIMAL(10,2), -- null for OPEN
  swap DECIMAL(10,2),
  commission DECIMAL(10,2),
  comment TEXT,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_trades_ticket_action ON trades(ticket, action);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
```

**Do this to avoid bugs:** Enable RLS immediately after table creation.

## 3. Bridge Environment & Loop

```bash
# .env (Windows machine only - never commit)
SUPABASE_URL=https://hmehzemjfgahqyoljdps.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhtZWh6ZW1qZmdhaHF5b2xqZHBzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTUxNTYzMCwiZXhwIjoyMDcxMDkxNjMwfQ.l_QsgCCr0acukJnq9xa_QURogJanjryy_IaQVHrwSM4
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo
UPDATE_MS=1000
```

### Python Bridge Structure

**mt5_client.py:**
```python
def initialize_mt5() -> bool
def get_open_positions() -> List[Dict]
def get_account_info() -> Dict
def get_closed_deals_since(timestamp) -> List[Dict]  # For close detection
```

**supabase_client.py:**
```python
def upsert_positions(positions: List[Dict]) -> None
def append_trade(trade_data: Dict) -> None
def get_last_close_check() -> datetime  # Track close detection cursor
```

**main.py:**
```python
def detect_closes(seen_tickets: Set[int], current_tickets: Set[int]) -> List[int]:
    """Returns tickets that were open but now missing"""
    return seen_tickets - current_tickets

def process_closed_tickets(closed_tickets: List[int]) -> None:
    """Fetch close info from history_deals_get, append to trades"""
    
def main_loop():
    seen_open_tickets = set()
    while True:
        try:
            # 1. Upsert current positions
            positions = mt5_client.get_open_positions()
            supabase_client.upsert_positions(positions)
            
            # 2. Detect closes
            current_tickets = {p['ticket'] for p in positions}
            closed = detect_closes(seen_open_tickets, current_tickets)
            process_closed_tickets(closed)
            
            seen_open_tickets = current_tickets
            time.sleep(UPDATE_MS / 1000)
        except Exception as e:
            # Exponential backoff on errors
```

## 4. Run Commands

```bash
# Bridge (Windows)
cd bridge/
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py

# Frontend (any OS)
npm install
npm run dev
```

## 5. Frontend Realtime Wiring

### useLivePositions.ts

```typescript
import { useEffect, useState } from 'react'
import { supabase } from './supabase-client'

interface Position {
  ticket: number
  symbol: string
  type: number
  volume: number
  price_open: number
  price_current: number
  profit: number
  updated_at: string
}

export const useLivePositions = () => {
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Initial fetch
    const fetchPositions = async () => {
      const { data } = await supabase.from('positions').select('*')
      setPositions(data || [])
      setLoading(false)
    }

    // Realtime subscription
    const subscription = supabase
      .channel('positions-channel')
      .on('postgres_changes', 
          { event: '*', schema: 'public', table: 'positions' },
          (payload) => {
            if (payload.eventType === 'INSERT' || payload.eventType === 'UPDATE') {
              setPositions(prev => {
                const updated = prev.filter(p => p.ticket !== payload.new.ticket)
                return [...updated, payload.new as Position]
              })
            }
            if (payload.eventType === 'DELETE') {
              setPositions(prev => prev.filter(p => p.ticket !== payload.old.ticket))
            }
          })
      .subscribe()

    fetchPositions()
    return () => { subscription.unsubscribe() }
  }, [])

  return { positions, loading }
}
```

### Trade Events Subscription

```typescript
// Subscribe to new trade events (opens/closes)
const { data: trades } = await supabase
  .from('trades')
  .select('*')
  .order('timestamp', { ascending: false })
  .limit(50)

const tradesSubscription = supabase
  .channel('trades-channel')
  .on('postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'trades' },
      (payload) => console.log('New trade:', payload.new))
  .subscribe()
```

## 6. IDs & Duplicate Prevention

### Idempotency Keys
- Positions: `ticket` (natural PK, upsert by ticket)
- Trades: Use `(ticket, action, timestamp)` uniqueness check before insert
- Close detection: Track `last_close_check_timestamp` to avoid reprocessing

**Do this to avoid bugs:** Always upsert positions; never insert duplicates in trades table.

## 7. Security Checklist

```sql
-- RLS Policies (run after table creation)
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;

-- Allow anon read-only access
CREATE POLICY "Allow read access" ON positions FOR SELECT TO anon USING (true);
CREATE POLICY "Allow read access" ON trades FOR SELECT TO anon USING (true);

-- Block anon writes (service role bypasses RLS)
CREATE POLICY "Block anon writes" ON positions FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "Block anon writes" ON trades FOR INSERT TO anon WITH CHECK (false);
```

### Key Management
- Bridge: Uses `SERVICE_ROLE_KEY` (full access, server-only)
- Frontend: Uses `ANON_KEY` (read-only via RLS): `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhtZWh6ZW1qZmdhaHF5b2xqZHBzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU1MTU2MzAsImV4cCI6MjA3MTA5MTYzMH0.fPDbZLmYWgIJdxb-mUSV4m5vDw1bBsEQo4lq2t_9FF0`
- **Never** expose service key to browser/frontend

## 8. Resilience Recommendations

### Heartbeat & Health

```python
# Add to main loop
def send_heartbeat():
    supabase.table('bridge_status').upsert({
        'id': 1, 
        'last_seen': datetime.utcnow().isoformat(),
        'status': 'healthy'
    })
```

### Error Handling
- MT5 connection drops: `mt5.initialize()` retry with exponential backoff
- Supabase timeouts: Retry with jitter, max 3 attempts
- Network failures: Continue loop, log errors, don't crash

**Do this to avoid bugs:** Always reinitialize MT5 connection on first error.

## 9. Test Checklist

- [ ] Bridge connects to MT5 and Supabase
- [ ] Open position appears in React app within `UPDATE_MS`
- [ ] Position updates (profit/loss) reflect in realtime
- [ ] Position close creates trade record with `action='CLOSE'`
- [ ] No duplicate trades on bridge restart
- [ ] RLS blocks frontend writes, allows reads
- [ ] Bridge survives MT5 disconnect/reconnect
- [ ] Realtime subscription reconnects after network drop

## 10. Repo Structure Check

```
├── bridge/
│   ├── .env (service key here)
│   ├── main.py
│   ├── mt5_client.py
│   └── supabase_client.py
├── frontend/
│   ├── .env.local (anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...)
│   ├── hooks/useLivePositions.ts
│   └── lib/supabase-client.ts
└── sql/schema.sql
```

### What to Verify in Existing Repo
- Positions table has upsert logic (not insert)
- Bridge tracks seen tickets for close detection
- Frontend uses anon key only
- RLS policies are enabled
- Realtime subscription handles reconnection