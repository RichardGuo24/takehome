import { useCallback, useEffect, useState } from 'react'

// Calls `fetcher` now and then every `intervalMs`. `refresh` re-fetches immediately,
// e.g. right after the user submits an order. A tiny stand-in for a data library.
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 1500) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)

  const refresh = useCallback(async () => {
    try {
      setData(await fetcher())
      setError(null)
    } catch (err) {
      setError(err)
    }
  }, [fetcher])

  useEffect(() => {
    // Polling the backend is synchronizing with an external system; state is set
    // only after the fetch resolves, not synchronously.
    // oxlint-disable-next-line react/set-state-in-effect
    void refresh()
    const id = setInterval(() => void refresh(), intervalMs)
    return () => clearInterval(id)
  }, [refresh, intervalMs])

  return { data, error, refresh }
}
