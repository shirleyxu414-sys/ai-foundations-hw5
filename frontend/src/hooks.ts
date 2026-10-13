import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { AgentEvent } from './types'

/** Call `fn` now and then every `ms` milliseconds. `refresh` runs it again right away. */
export function usePoll<T>(fn: () => Promise<T>, ms: number) {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<string | null>(null)
  const fnRef = useRef(fn)
  useEffect(() => {
    fnRef.current = fn
  })

  const refresh = useCallback(async () => {
    try {
      setData(await fnRef.current())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    let stop = false
    let timer = 0
    const loop = async () => {
      await refresh()
      if (!stop) timer = window.setTimeout(loop, ms)
    }
    loop()
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
  }, [refresh, ms])

  return { data, error, refresh }
}

/**
 * The agent events for one ticket. The first call gets the latest events; after that only newer ones
 * are fetched, using the cursor the backend hands back. `refresh` pulls immediately.
 */
export function useEventStream(ticketId: number | null, ms: number) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [total, setTotal] = useState(0)
  const cursor = useRef<number | undefined>(undefined)
  const [owner, setOwner] = useState<number | null>(null)

  const pull = useCallback(async () => {
    if (ticketId === null) return
    const page = await api.events({ ticketId, after: cursor.current })
    cursor.current = page.next_cursor
    setTotal(page.total)
    setOwner(ticketId)
    if (page.events.length) {
      setEvents((prev) => {
        const seen = new Set(prev.map((e) => e.id))
        return [...prev, ...page.events.filter((e) => !seen.has(e.id))]
      })
    }
  }, [ticketId])

  useEffect(() => {
    cursor.current = undefined
    setEvents([])
    if (ticketId === null) return
    let stop = false
    let timer = 0
    const loop = async () => {
      try {
        await pull()
      } catch {
        /* the tickets poll shows the connection error */
      }
      if (!stop) timer = window.setTimeout(loop, ms)
    }
    loop()
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
  }, [ticketId, ms, pull])

  // never show one ticket's events under another ticket while the new ones load
  return { events: owner === ticketId ? events : [], total, refresh: pull }
}
