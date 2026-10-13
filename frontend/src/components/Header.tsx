import { useEffect, useRef, useState } from 'react'
import { money } from '../derive'
import type { Cash } from '../types'

interface Props {
  cash: Cash | undefined
  backendError: string | null
  canReset: boolean
  onReset: () => Promise<void>
}

export default function Header({ cash, backendError, canReset, onReset }: Props) {
  const prev = useRef<number | undefined>(undefined)
  const [drop, setDrop] = useState<number | null>(null)
  const [flash, setFlash] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)

  // When the balance goes down (an approved payment), show how much it dropped for a few seconds.
  useEffect(() => {
    if (cash === undefined) return
    const before = prev.current
    prev.current = cash.balance
    if (before === undefined || before === cash.balance) return
    setDrop(cash.balance - before)
    setFlash(true)
    const t1 = window.setTimeout(() => setFlash(false), 1600)
    const t2 = window.setTimeout(() => setDrop(null), 8000)
    return () => {
      window.clearTimeout(t1)
      window.clearTimeout(t2)
    }
  }, [cash])

  useEffect(() => {
    if (!confirm) return
    const t = window.setTimeout(() => setConfirm(false), 4000)
    return () => window.clearTimeout(t)
  }, [confirm])

  const reset = async () => {
    if (!confirm) return setConfirm(true)
    setConfirm(false)
    setBusy(true)
    try {
      await onReset()
    } finally {
      setBusy(false)
    }
  }

  return (
    <header className="top">
      <div className="top-row">
        <div>
          <div className="eyebrow">Campus Customs · Agent Desk</div>
          <h1>
            The shop that <em>runs itself</em>
          </h1>
        </div>

        <div className={`balance ${flash ? 'flash' : ''}`} aria-live="polite">
          <div className="k">Checking balance{cash ? ` · ${cash.date}` : ''}</div>
          <div className="vrow">
            <div className="v mono">{cash ? money(cash.balance) : '—'}</div>
            {drop !== null && (
              <span className={`drop mono ${drop < 0 ? 'down' : 'up'}`} aria-label={drop < 0 ? 'Cash went out' : 'Balance went up'}>
                {drop < 0 ? '−' : '+'}
                {money(Math.abs(drop))}
              </span>
            )}
          </div>
          {cash?.starting_balance != null && <div className="start">Started at {money(cash.starting_balance)} after the last reset</div>}
          <div className="n">
            {cash && cash.pending_approvals_total > 0
              ? `${money(cash.pending_approvals_total)} waiting for approval → ${money(cash.balance_after_pending)} after`
              : 'nothing waiting for approval'}
          </div>
        </div>

        <div className="top-actions">
          <button
            className={`btn ghost ${confirm ? 'warn' : ''}`}
            disabled={!canReset || busy}
            onClick={reset}
            title="Put the database back to its original values for a fresh run"
          >
            {busy ? 'Resetting…' : confirm ? 'Click again to reset' : 'Reset database'}
          </button>
          <span className={`link ${backendError ? 'down' : 'up'}`}>{backendError ? 'backend offline' : 'backend online'}</span>
        </div>
      </div>
    </header>
  )
}
