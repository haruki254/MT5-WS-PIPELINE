import { useEffect, useState, useCallback } from 'react'
import { 
  supabase, 
  BridgeStatus, 
  fetchBridgeStatus, 
  subscribeToBridgeStatus 
} from '../lib/supabase-client'
import type { RealtimeChannel } from '@supabase/supabase-js'

interface UseBridgeStatusReturn {
  status: BridgeStatus | null
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
  isHealthy: boolean
  isOffline: boolean
  isError: boolean
  lastSeenAgo: string
}

export const useBridgeStatus = (): UseBridgeStatusReturn => {
  const [status, setStatus] = useState<BridgeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Calculate derived values
  const isHealthy = status?.status === 'healthy'
  const isOffline = status?.status === 'offline'
  const isError = status?.status === 'error'

  // Calculate time since last seen
  const lastSeenAgo = status ? getTimeAgo(status.last_seen) : 'Unknown'

  // Fetch bridge status from database
  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const data = await fetchBridgeStatus()
      setStatus(data)
    } catch (err) {
      console.error('Error fetching bridge status:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch bridge status')
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
    console.log('Realtime bridge status update:', payload)
    
    const { eventType, new: newRecord } = payload

    if (eventType === 'UPDATE') {
      setStatus(newRecord as BridgeStatus)
    }
  }, [])

  useEffect(() => {
    let subscription: RealtimeChannel | null = null

    const initializeData = async () => {
      // Initial fetch
      await fetchData()

      // Set up realtime subscription
      try {
        subscription = subscribeToBridgeStatus(handleRealtimeUpdate)
        
        // Check subscription status
        subscription.on('system', {}, (payload) => {
          console.log('Bridge status subscription status:', payload)
        })

      } catch (err) {
        console.error('Error setting up bridge status realtime subscription:', err)
        setError('Failed to set up real-time bridge status updates')
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

  // Periodically refetch data as fallback (every 15 seconds)
  useEffect(() => {
    const interval = setInterval(() => {
      if (!loading) {
        fetchData()
      }
    }, 15000)

    return () => clearInterval(interval)
  }, [fetchData, loading])

  return {
    status,
    loading,
    error,
    refetch,
    isHealthy,
    isOffline,
    isError,
    lastSeenAgo
  }
}

// Utility function to calculate time ago
function getTimeAgo(dateString: string): string {
  const now = new Date()
  const past = new Date(dateString)
  const diffMs = now.getTime() - past.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSeconds < 60) {
    return `${diffSeconds} seconds ago`
  } else if (diffMinutes < 60) {
    return `${diffMinutes} minutes ago`
  } else if (diffHours < 24) {
    return `${diffHours} hours ago`
  } else {
    return `${diffDays} days ago`
  }
}