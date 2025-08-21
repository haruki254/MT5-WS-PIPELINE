-- MT5 to React via Supabase Schema
-- Run this in your Supabase SQL Editor

-- Enable realtime on public schema
ALTER PUBLICATION supabase_realtime ADD TABLE public.positions;
ALTER PUBLICATION supabase_realtime ADD TABLE public.trades;
ALTER PUBLICATION supabase_realtime ADD TABLE public.bridge_status;

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

-- Bridge status table (for heartbeat)
CREATE TABLE bridge_status (
  id INTEGER PRIMARY KEY,
  last_seen TIMESTAMPTZ DEFAULT NOW(),
  status VARCHAR(20) DEFAULT 'offline',
  positions_count INTEGER DEFAULT 0,
  last_close_check TIMESTAMPTZ
);

-- Indexes for performance
CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_trades_ticket_action ON trades(ticket, action);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);

-- RLS Policies (run after table creation)
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE bridge_status ENABLE ROW LEVEL SECURITY;

-- Allow anon read-only access
CREATE POLICY "Allow read access" ON positions FOR SELECT TO anon USING (true);
CREATE POLICY "Allow read access" ON trades FOR SELECT TO anon USING (true);
CREATE POLICY "Allow read access" ON bridge_status FOR SELECT TO anon USING (true);

-- Block anon writes (service role bypasses RLS)
CREATE POLICY "Block anon writes" ON positions FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "Block anon writes" ON trades FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "Block anon writes" ON bridge_status FOR INSERT TO anon WITH CHECK (false);