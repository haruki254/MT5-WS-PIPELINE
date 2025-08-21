import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables')
}

// Create Supabase client with anon key (read-only access via RLS)
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: false, // No user authentication needed
    autoRefreshToken: false,
    detectSessionInUrl: false
  },
  realtime: {
    params: {
      eventsPerSecond: 10 // Limit realtime events for performance
    }
  }
})

// Database Types
export interface Position {
  ticket: number
  symbol: string
  type: number // 0=buy, 1=sell
  volume: number
  price_open: number
  price_current: number | null
  profit: number | null
  swap: number | null
  commission: number | null
  comment: string | null
  updated_at: string
}

export interface Trade {
  id: number
  ticket: number
  action: 'OPEN' | 'CLOSE'
  symbol: string
  type: number
  volume: number
  price: number
  profit: number | null
  swap: number | null
  commission: number | null
  comment: string | null
  timestamp: string
}

export interface BridgeStatus {
  id: number
  last_seen: string
  status: 'healthy' | 'offline' | 'error'
  positions_count: number
  error_message: string | null
  updated_at: string
}

// Utility functions for formatting
export const formatPositionType = (type: number): string => {
  return type === 0 ? 'BUY' : 'SELL'
}

export const formatCurrency = (amount: number | null, currency = 'USD'): string => {
  if (amount === null || amount === undefined) return '-'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2
  }).format(amount)
}

export const formatVolume = (volume: number): string => {
  return volume.toFixed(2)
}

export const formatPrice = (price: number | null, digits = 5): string => {
  if (price === null || price === undefined) return '-'
  return price.toFixed(digits)
}

// Database query helpers
export const fetchPositions = async (): Promise<Position[]> => {
  const { data, error } = await supabase
    .from('positions')
    .select('*')
    .order('updated_at', { ascending: false })
  
  if (error) {
    console.error('Error fetching positions:', error)
    return []
  }
  
  return data || []
}

export const fetchRecentTrades = async (limit = 50): Promise<Trade[]> => {
  const { data, error } = await supabase
    .from('trades')
    .select('*')
    .order('timestamp', { ascending: false })
    .limit(limit)
  
  if (error) {
    console.error('Error fetching trades:', error)
    return []
  }
  
  return data || []
}

export const fetchBridgeStatus = async (): Promise<BridgeStatus | null> => {
  const { data, error } = await supabase
    .from('bridge_status')
    .select('*')
    .eq('id', 1)
    .single()
  
  if (error) {
    console.error('Error fetching bridge status:', error)
    return null
  }
  
  return data
}

// Realtime subscription helpers
export const subscribeToPositions = (
  callback: (payload: any) => void
) => {
  return supabase
    .channel('positions-channel')
    .on(
      'postgres_changes',
      { event: '*', schema: 'public', table: 'positions' },
      callback
    )
    .subscribe()
}

export const subscribeToTrades = (
  callback: (payload: any) => void
) => {
  return supabase
    .channel('trades-channel')
    .on(
      'postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'trades' },
      callback
    )
    .subscribe()
}

export const subscribeToBridgeStatus = (
  callback: (payload: any) => void
) => {
  return supabase
    .channel('bridge-status-channel')
    .on(
      'postgres_changes',
      { event: 'UPDATE', schema: 'public', table: 'bridge_status' },
      callback
    )
    .subscribe()
}