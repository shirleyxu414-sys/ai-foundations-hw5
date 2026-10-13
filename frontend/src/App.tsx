import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { latestRunId, runOutcome } from './derive'
import { useEventStream, usePoll } from './hooks'
import type { Continued, Payment } from './types'
import Header from './components/Header'
import TicketList from './components/TicketList'
import RunBanner from './components/RunBanner'
import { AgentBoard, Summaries } from './components/AgentBoard'
import Feed from './components/Feed'
import Approvals from './components/Approvals'
import DecisionBox from './components/DecisionBox'

const HIDE_KEY = 'campus.hideBefore'

interface Notice {
  kind: 'error' | 'info'
  text: string
}

export default function App() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [feedFilter, setFeedFilter] = useState('all')
  const [notice, setNotice] = useState<Notice | null>(null)
  const [starting, setStarting] = useState(false)
  // After a reset the old runs stay in the audit trail; this hides them from the board.
  const [hideBefore, setHideBefore] = useState<number>(() => Number(localStorage.getItem(HIDE_KEY) ?? 0))

  // Poll faster while the agents are running.
  const [busy, setBusy] = useState(false)
  const slow = busy ? 1500 : 4000
  const tickets = usePoll(api.tickets, slow)
  const cash = usePoll(api.cash, slow)
  const approvals = usePoll(api.approvals, slow)
  const stream = useEventStream(selectedId, busy ? 1000 : 4000)

  const ticketList = useMemo(() => tickets.data ?? [], [tickets.data])
  const anyRunning = ticketList.some((t) => t.running)
  useEffect(() => setBusy(anyRunning), [anyRunning])

  useEffect(() => {
    if (selectedId === null && ticketList.length > 0) setSelectedId((ticketList.find((t) => t.running) ?? ticketList[0]).id)
  }, [selectedId, ticketList])

  const refreshAll = useCallback(() => {
    tickets.refresh()
    cash.refresh()
    approvals.refresh()
    stream.refresh().catch(() => undefined)
  }, [tickets, cash, approvals, stream])

  // When a run finishes, pull everything once more so the board settles on the final state.
  const wasRunning = useRef(false)
  useEffect(() => {
    if (wasRunning.current && !anyRunning) refreshAll()
    wasRunning.current = anyRunning
  }, [anyRunning, refreshAll])

  const selected = ticketList.find((t) => t.id === selectedId) ?? null
  const events = useMemo(() => stream.events.filter((e) => e.id >= hideBefore), [stream.events, hideBefore])
  const runId = latestRunId(events)
  const runEvents = useMemo(() => events.filter((e) => e.run_id === runId), [events, runId])
  const outcome = runOutcome(runEvents, selected?.running ?? false)

  // The activity filter always starts from "everyone": when a different ticket is shown, when a new run begins
  // (a new run id), and when a run starts or ends. It never stays on an agent from an earlier view.
  useEffect(() => setFeedFilter('all'), [selectedId, runId, anyRunning])

  const startRun = async () => {
    if (!selected) return
    setStarting(true)
    setNotice(null)
    try {
      await api.runTicket(selected.id)
      setFeedFilter('all')
      setBusy(true)
      refreshAll()
    } catch (e) {
      setNotice({ kind: 'error', text: e instanceof ApiError ? e.message : String(e) })
    } finally {
      setStarting(false)
    }
  }

  // After a person acts, the team picks the ticket up again by itself. Say so, and show that ticket.
  const followUp = (r: Continued): string => (r.continued_ticket_id !== null ? ` The team is picking ticket ${r.continued_ticket_id} back up now.` : '')
  const pickUp = (r: Continued) => {
    if (r.continued_ticket_id === null) return
    setSelectedId(r.continued_ticket_id)
    setBusy(true)
  }

  const approve = async (id: number, approvedBy: string): Promise<Payment> => {
    const payment = await api.approve(id, approvedBy)
    setNotice({
      kind: 'info',
      text: `${approvedBy} approved the payment: ${payment.amount.toLocaleString('en-US', { style: 'currency', currency: 'USD' })} paid. Checking balance is now ${payment.balance_after.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}.${followUp(payment)}`,
    })
    pickUp(payment)
    refreshAll()
    return payment
  }

  const decline = async (id: number, declinedBy: string) => {
    const r = await api.decline(id, declinedBy)
    setNotice({ kind: 'info', text: `${declinedBy} declined approval ${id}. No money moved.${followUp(r)}` })
    pickUp(r)
    refreshAll()
  }

  const receive = async (id: number, receivedBy: string) => {
    const r = await api.receive(id, receivedBy)
    setNotice({ kind: 'info', text: `${receivedBy} confirmed the delivery: ${r.qty_received} × ${r.sku} size ${r.size}. In stock: ${r.qty_on_hand_before} → ${r.qty_on_hand_after}.${followUp(r)}` })
    pickUp(r)
    refreshAll()
  }

  const decide = async (ticketId: number, decidedBy: string, decision: string) => {
    const r = await api.decide(ticketId, decidedBy, decision)
    setNotice({ kind: 'info', text: `${decidedBy} recorded a decision on ticket ${ticketId}.${followUp(r)}` })
    pickUp(r)
    refreshAll()
  }

  // Choosing an agent on a card filters the activity feed far below it, so bring the feed into view.
  const feedRef = useRef<HTMLDivElement>(null)
  const pickAgent = (name: string) => {
    setFeedFilter(name)
    if (name === 'all') return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    requestAnimationFrame(() => feedRef.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' }))
  }

  const reset = async () => {
    try {
      await api.reset()
      const page = await api.events({ limit: 1 })
      localStorage.setItem(HIDE_KEY, String(page.total))
      setHideBefore(page.total)
      setNotice({ kind: 'info', text: 'Database reset to the original values. The audit trail keeps the earlier runs.' })
      refreshAll()
    } catch (e) {
      setNotice({ kind: 'error', text: e instanceof ApiError ? e.message : String(e) })
    }
  }

  const backendError = tickets.error ?? cash.error ?? null

  return (
    <>
      <Header cash={cash.data} backendError={backendError} canReset={!anyRunning} onReset={reset} />
      <main>
        {backendError && (
          <div className="notice error" role="alert">
            {backendError} Start it from the backend folder with <code>uvicorn main:app --reload --port 8000</code>.
          </div>
        )}
        {notice && (
          <div className={`notice ${notice.kind}`} role="status">
            {notice.text}
            <button className="x" onClick={() => setNotice(null)} aria-label="Dismiss">
              ×
            </button>
          </div>
        )}
        <div className="grid">
          <aside className="side">
            <TicketList
              tickets={ticketList}
              approvals={approvals.data ?? []}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id)
                setFeedFilter('all')
              }}
            />
            <Approvals approvals={approvals.data ?? []} balance={cash.data?.balance} onApprove={approve} onDecline={decline} onReceive={receive} onSelectTicket={setSelectedId} />
          </aside>
          <div className="stage">
            {selected ? (
              <>
                <RunBanner
                  ticket={selected}
                  outcome={outcome}
                  approvals={approvals.data ?? []}
                  anyRunning={anyRunning}
                  starting={starting}
                  onRun={startRun}
                />
                <DecisionBox ticketId={selected.id} onDecide={decide} />
                <AgentBoard runEvents={runEvents} filter={feedFilter} onFilter={pickAgent} />
                <Summaries runEvents={runEvents} runState={outcome.state} />
                <div ref={feedRef} className="scroll-target">
                  <Feed runEvents={runEvents} filter={feedFilter} onFilter={setFeedFilter} />
                </div>
              </>
            ) : (
              <section className="panel">
                <p className="empty">{tickets.error ? 'Waiting for the backend…' : 'Loading tickets…'}</p>
              </section>
            )}
          </div>
        </div>
      </main>
      <footer>
        Agents only prepare payments. A human approves, and then the cash moves. Every step is saved to output/audit_trail.json.
      </footer>
    </>
  )
}
