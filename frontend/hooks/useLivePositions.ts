import { useEffect, useState, useCallback } from 'react'
import { 
  supabase, 
  Position, 
  fetchPositions, 
  subscribeToPositions 
} from '../lib/supabase-client'
import type { RealtimeChannel } from '@supabase/supabase-js'

interface UseLivePositionsReturn {
  positions: Position[]
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
  totalProfit: number
  totalVolume: number
  positionCount: number
}

export const useLivePositions = (): UseLivePositionsReturn => {
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Calculate derived values
  const totalProfit = positions.reduce((sum, pos) => sum + (pos.profit || 0), 0)
  const totalVolume = positions.reduce((sum, pos) => sum + pos.volume, 0)
  const positionCount = positions.length

  // Fetch positions from database
  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const data = await fetchPositions()
      setPositions(data)
    } catch (err) {
      console.error('Error fetching positions:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch positions')
    } finally {
      setLoading(false)
    }
  }, [])

  // Manual refetch function
  const refetch = useCallback(async () => {
    setLoading(true)
    await fetchData()
  }, [fetchData])

  // Handle realtime updates
  const handleRealtimeUpdate = useCallback((payload: any) => {
    console.log('Realtime position update:', payload)
    
    const { eventType, new: newRecord, old: oldRecord } = payload

    setPositions(prevPositions => {
      switch (eventType) {
        case 'INSERT':
          // Add new position if it doesn't exist
          const existsInsert = prevPositions.some(p => p.ticket === newRecord.ticket)
          if (!existsInsert) {
            return [...prevPositions, newRecord as Position]
          }
          return prevPositions

        case 'UPDATE':
          // Update existing position
          return prevPositions.map(pos =>
            pos.ticket === newRecord.ticket ? (newRecord as Position) : pos
          )

        case 'DELETE':
          // Remove deleted position
          return prevPositions.filter(pos => pos.ticket !== oldRecord.ticket)

        default:
          return prevPositions
      }
    })
  }, [])

  useEffect(() => {
    let subscription: RealtimeChannel | null = null

    const initializeData = async () => {
      // Initial fetch
      await fetchData()

      // Set up realtime subscription
      try {
        subscription = subscribeToPositions(handleRealtimeUpdate)
        
        // Check subscription status
        subscription.on('system', {}, (payload) => {
          console.log('Subscription status:', payload)
        })

      } catch (err) {
        console.error('Error setting up realtime subscription:', err)
        setError('Failed to set up real-time updates')
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

  // Periodically refetch data as fallback (every 30 seconds)
  useEffect(() => {
    const interval = setInterval(() => {
      if (!loading) {
        fetchData()
      }
    }, 30000)

    return () => clearInterval(interval)
  }, [fetchData, loading])

  return {
    positions,
    loading,
    error,
    refetch,
    totalProfit,
    totalVolume,
    positionCount
  }
}

// Additional hook for individual position tracking
export const usePosition = (ticket: number) => {
  const { positions } = useLivePositions()
  
  const position = positions.find(p => p.ticket === ticket)
  
  return {
    position,
    exists: !!position,
    isProfit: position ? (position.profit || 0) > 0 : false,
    isLoss: position ? (position.profit || 0) < 0 : false
  }
}

// Hook for positions filtered by symbol
export const usePositionsBySymbol = (symbol?: string) => {
  const { positions, loading, error, refetch } = useLivePositions()
  
  const filteredPositions = symbol 
    ? positions.filter(p => p.symbol === symbol)
    : positions

  const symbolProfit = filteredPositions.reduce((sum, pos) => sum + (pos.profit || 0), 0)
  const symbolVolume = filteredPositions.reduce((sum, pos) => sum + pos.volume, 0)

  return {
    positions: filteredPositions,
    loading,
    error,
    refetch,
    totalProfit: symbolProfit,
    totalVolume: symbolVolume,
    positionCount: filteredPositions.length
  }
}