import { useEffect, useState, useCallback } from 'react'
import { 
  supabase, 
  Trade, 
  fetchRecentTrades, 
  subscribeToTrades 
} from '../lib/supabase-client'
import type { RealtimeChannel } from '@supabase/supabase-js'

interface UseLiveTradesReturn {
  trades: Trade[]
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
  totalTrades: number
  openTrades: Trade[]
  closeTrades: Trade[]
}

export const useLiveTrades = (limit = 50): UseLiveTradesReturn => {
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Calculate derived values
  const totalTrades = trades.length
  const openTrades = trades.filter(trade => trade.action === 'OPEN')
  const closeTrades = trades.filter(trade => trade.action === 'CLOSE')

  // Fetch trades from database
  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const data = await fetchRecentTrades(limit)
      setTrades(data)
    } catch (err) {
      console.error('Error fetching trades:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch trades')
    } finally {
      setLoading(false)
    }
  }, [limit])

  // Manual refetch function
  const refetch = useCallback(async () => {
    setLoading(true)
    await fetchData()
  }, [fetchData])

  // Handle realtime updates for new trades
  const handleRealtimeUpdate = useCallback((payload: any) => {
    console.log('Realtime trade update:', payload)
    
    const { eventType, new: newRecord } = payload

    if (eventType === 'INSERT') {
      setTrades(prevTrades => {
        // Add new trade at the beginning (most recent first)
        const newTrades = [newRecord as Trade, ...prevTrades]
        // Keep only the specified limit
        return newTrades.slice(0, limit)
      })
    }
  }, [limit])

  useEffect(() => {
    let subscription: RealtimeChannel | null = null

    const initializeData = async () => {
      // Initial fetch
      await fetchData()

      // Set up realtime subscription
      try {
        subscription = subscribeToTrades(handleRealtimeUpdate)
        
        // Check subscription status
        subscription.on('system', {}, (payload) => {
          console.log('Trades subscription status:', payload)
        })

      } catch (err) {
        console.error('Error setting up trades realtime subscription:', err)
        setError('Failed to set up real-time trade updates')
      }
    }

    initializeData()

    // Cleanup subscription on unmount
    return () => {
      if (subscription) {
        subscription.unsubscribe()
      }
    }
  }, [fetchData, handleRealtimeUpdate])

  return {
    trades,
    loading,
    error,
    refetch,
    totalTrades,
    openTrades,
    closeTrades
  }
}

// Hook for trades filtered by ticket
export const useTradesByTicket = (ticket: number) => {
  const { trades, loading, error } = useLiveTrades()
  
  const ticketTrades = trades.filter(trade => trade.ticket === ticket)
  const openTrade = ticketTrades.find(trade => trade.action === 'OPEN')
  const closeTrade = ticketTrades.find(trade => trade.action === 'CLOSE')
  
  return {
    trades: ticketTrades,
    openTrade,
    closeTrade,
    isComplete: !!(openTrade && closeTrade),
    loading,
    error
  }
}