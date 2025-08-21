-- MT5 to React via Supabase: Database Schema
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

-- Bridge status table for heartbeat monitoring
CREATE TABLE bridge_status (
  id INTEGER PRIMARY KEY DEFAULT 1,
  last_seen TIMESTAMPTZ NOT NULL,
  status VARCHAR(20) NOT NULL, -- 'healthy', 'offline', 'error'
  positions_count INTEGER DEFAULT 0,
  error_message TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT single_row CHECK (id = 1)
);

-- Indexes for performance
CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_positions_updated_at ON positions(updated_at DESC);
CREATE INDEX idx_trades_ticket_action ON trades(ticket, action);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX idx_trades_symbol ON trades(symbol);

-- Unique constraint to prevent duplicate trade records
CREATE UNIQUE INDEX idx_trades_unique ON trades(ticket, action, timestamp);

-- Enable Row Level Security
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE bridge_status ENABLE ROW LEVEL SECURITY;

-- RLS Policies for read-only anon access
CREATE POLICY "Allow read access" ON positions FOR SELECT TO anon USING (true);
CREATE POLICY "Allow read access" ON trades FOR SELECT TO anon USING (true);
CREATE POLICY "Allow read access" ON bridge_status FOR SELECT TO anon USING (true);

-- Block anon writes (service role bypasses RLS)
CREATE POLICY "Block anon writes" ON positions FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "Block anon writes" ON positions FOR UPDATE TO anon USING (false);
CREATE POLICY "Block anon writes" ON positions FOR DELETE TO anon USING (false);

CREATE POLICY "Block anon writes" ON trades FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "Block anon writes" ON trades FOR UPDATE TO anon USING (false);
CREATE POLICY "Block anon writes" ON trades FOR DELETE TO anon USING (false);

CREATE POLICY "Block anon writes" ON bridge_status FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "Block anon writes" ON bridge_status FOR UPDATE TO anon USING (false);
CREATE POLICY "Block anon writes" ON bridge_status FOR DELETE TO anon USING (false);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to automatically update timestamps
CREATE TRIGGER update_positions_updated_at 
    BEFORE UPDATE ON positions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bridge_status_updated_at 
    BEFORE UPDATE ON bridge_status 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert initial bridge status record
INSERT INTO bridge_status (id, last_seen, status, positions_count) 
VALUES (1, NOW(), 'offline', 0)
ON CONFLICT (id) DO NOTHING;