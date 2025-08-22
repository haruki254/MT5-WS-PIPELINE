# MT5 to React via Supabase - Setup Guide

This guide will help you set up the complete MT5 to React integration using Supabase for real-time data synchronization.

## Quick Setup Checklist

- [ ] Run SQL schema in Supabase
- [ ] Configure bridge environment
- [ ] Configure frontend environment
- [ ] Install dependencies
- [ ] Start bridge and frontend

## 1. Database Setup

### Run SQL Schema
1. Open your Supabase project: https://hmehzemjfgahqyoljdps.supabase.co
2. Go to SQL Editor
3. Copy and paste the contents of `sql/schema.sql`
4. Execute the SQL to create tables and policies

### Verify Tables Created
- `positions` - Current open positions (upserted by ticket)
- `trades` - Trade history (append-only for opens/closes)
- `bridge_status` - Bridge heartbeat monitoring

## 2. Bridge Setup (Windows/MT5 Machine)

### Install Dependencies
```bash
cd bridge/
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### Configure Environment
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

Required variables in `.env`:
```
SUPABASE_URL=https://hmehzemjfgahqyoljdps.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhtZWh6ZW1qZmdhaHF5b2xqZHBzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTUxNTYzMCwiZXhwIjoyMDcxMDkxNjMwfQ.l_QsgCCr0acukJnq9xa_QURogJanjryy_IaQVHrwSM4
MT5_LOGIN=your_mt5_login
MT5_PASSWORD=your_mt5_password
MT5_SERVER=your_mt5_server
UPDATE_MS=1000
```

### Run Bridge
```bash
python main.py
```

## 3. Frontend Setup

### Install Dependencies
```bash
cd frontend/
npm install
```

### Configure Environment
```bash
cp .env.local.example .env.local
# Edit .env.local with your values
```

Required variables in `.env.local`:
```
NEXT_PUBLIC_SUPABASE_URL=https://hmehzemjfgahqyoljdps.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhtZWh6ZW1qZmdhaHF5b2xqZHBzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU1MTU2MzAsImV4cCI6MjA3MTA5MTYzMH0.fPDbZLmYWgIJdxb-mUSV4m5vDw1bBsEQo4lq2t_9FF0
```

### Run Frontend
```bash
npm run dev
```

## 4. Usage Examples

### Basic Position Monitoring
```typescript
import { useLivePositions } from './hooks/useLivePositions'

function PositionsTable() {
  const { positions, loading, totalProfit } = useLivePositions()
  
  if (loading) return <div>Loading...</div>
  
  return (
    <div>
      <h2>Total P&L: ${totalProfit.toFixed(2)}</h2>
      {positions.map(position => (
        <div key={position.ticket}>
          {position.symbol} - {position.volume} lots - ${position.profit?.toFixed(2)}
        </div>
      ))}
    </div>
  )
}
```

### Trade History
```typescript
import { useLiveTrades } from './hooks/useLiveTrades'

function TradesHistory() {
  const { trades, openTrades, closeTrades } = useLiveTrades(100)
  
  return (
    <div>
      <p>Opens: {openTrades.length}, Closes: {closeTrades.length}</p>
      {trades.map(trade => (
        <div key={trade.id}>
          {trade.action} {trade.symbol} at {trade.price}
        </div>
      ))}
    </div>
  )
}
```

### Bridge Status Monitor
```typescript
import { useBridgeStatus } from './hooks/useBridgeStatus'

function BridgeMonitor() {
  const { status, isHealthy, lastSeenAgo } = useBridgeStatus()
  
  return (
    <div>
      <div className={isHealthy ? 'green' : 'red'}>
        Bridge: {status?.status} ({lastSeenAgo})
      </div>
      <div>Positions: {status?.positions_count}</div>
    </div>
  )
}
```

## 5. Security Notes

- **Bridge**: Uses service role key (full access) - keep secure
- **Frontend**: Uses anon key (read-only via RLS) - safe for browser
- **RLS**: Prevents frontend from writing data
- **Environment**: Never commit `.env` or `.env.local` files

## 6. Troubleshooting

### Bridge Issues
- Check MT5 terminal is running and logged in
- Verify MT5 credentials in `.env`
- Check bridge logs in `bridge.log`
- Ensure Supabase service key is correct

### Frontend Issues
- Verify anon key in `.env.local`
- Check browser console for errors
- Test Supabase connection in Network tab
- Ensure realtime is enabled on tables

### Database Issues
- Verify RLS policies are created
- Check table permissions
- Ensure realtime publication includes tables
- Monitor Supabase logs for errors

## 7. Production Deployment

### Bridge (Windows Service)
- Use task scheduler or Windows service
- Add proper logging and monitoring
- Implement automatic restart on failure

### Frontend (Vercel/Netlify)
- Deploy with environment variables
- Enable automatic deployments
- Monitor performance and errors

### Database (Supabase)
- Monitor usage and performance
- Set up alerts for downtime
- Regular backups recommended

## File Structure Reference

```
├── bridge/
│   ├── .env (your credentials)
│   ├── main.py (main bridge logic)
│   ├── mt5_client.py (MT5 integration)
│   ├── supabase_client.py (database operations)
│   └── requirements.txt (dependencies)
├── frontend/
│   ├── .env.local (your config)
│   ├── lib/supabase-client.ts (database client)
│   ├── hooks/useLivePositions.ts (positions hook)
│   ├── hooks/useLiveTrades.ts (trades hook)
│   └── hooks/useBridgeStatus.ts (status hook)
└── sql/schema.sql (database schema)
```