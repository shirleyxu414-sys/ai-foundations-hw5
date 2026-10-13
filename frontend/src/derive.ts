// Turns the raw audit events from /api/events into what the board shows.
import type { AgentEvent, AgentName, AgentReport, Approval, Ticket, TicketDecision } from './types'

export const AGENTS: { name: AgentName; label: string; role: string; glyph: string }[] = [
  { name: 'boss', label: 'Boss', role: 'triages, assigns, decides', glyph: 'B' },
  { name: 'inventory', label: 'Inventory', role: 'stock and vendors', glyph: 'I' },
  { name: 'accounting', label: 'Accounting', role: 'cash, invoices, margins', glyph: 'A' },
  { name: 'facilities', label: 'Facilities', role: 'leases and rent', glyph: 'F' },
  { name: 'customer_service', label: 'Customer Service', role: 'drafts customer messages', glyph: 'C' },
]

export const agentLabel = (name: string | null): string =>
  AGENTS.find((a) => a.name === name)?.label ?? (name === 'human' ? 'Human' : (name ?? 'Team'))

export const money = (n: number): string =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export function brief(value: unknown, max = 150): string {
  const s = typeof value === 'string' ? value : JSON.stringify(value)
  if (s === undefined) return ''
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}

const clock = (iso: string): string =>
  new Date(iso).toLocaleTimeString('en-US', { hour12: false })
export { clock }

// ---------------------------------------------------------------- shapes inside `detail`

interface ToolCall {
  tool: string
  call_id: string
  args: Record<string, unknown>
}
const toolCalls = (e: AgentEvent): ToolCall[] => (e.detail.tool_calls as ToolCall[] | undefined) ?? []
const textOf = (e: AgentEvent): string[] => (e.detail.text as string[] | undefined) ?? []
const calleeOf = (tool: string): string | null => (tool.startsWith('ask_') ? tool.slice(4) : null)

function reportText(raw: unknown): string | null {
  try {
    const obj = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (obj && typeof obj === 'object') {
      const o = obj as Record<string, unknown>
      return (o.summary as string) ?? (o.decision as string) ?? null
    }
  } catch {
    /* not JSON */
  }
  return null
}


// ---------------------------------------------------------------- tools in plain words
// The feed says what happened in a sentence. (The full raw record of every call and result is in output/audit_trail.json.)

const STATUS_WORDS: Record<string, string> = {
  open: 'open', in_progress: 'in progress', waiting_approval: 'waiting for approval', resolved: 'resolved',
}
export const statusWords = (s: unknown): string => STATUS_WORDS[String(s)] ?? String(s).replace(/_/g, ' ')

const CODE_WORDS: Record<string, string> = {
  ...STATUS_WORDS, rent_notice: 'rent notice', customer_order: 'customer order', price_override: 'price override',
  purchase_order: 'purchase order', next_due: 'next due date', ticket_id: 'ticket', approved_by: 'approved by',
}
/** Shows a system word as ordinary words ("rent_notice" becomes "rent notice"). Display only; the data is untouched. */
export const plain = (text: string): string => text.replace(/\b[a-z]+(?:_[a-z]+)+\b/g, (m) => CODE_WORDS[m] ?? m.replace(/_/g, ' '))

const plural = (n: number, one: string, many = one + 's'): string => `${n} ${n === 1 ? one : many}`
const str = (v: unknown): string => (v === undefined || v === null ? '' : String(v))
const num = (v: unknown): number => (typeof v === 'number' ? v : Number(v) || 0)
const list = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? (v as Record<string, unknown>[]) : [])

/** "an invoice", "rent", or "a purchase order": what a payment is for. */
function paymentFor(kind: unknown, ref: unknown, args?: Record<string, unknown>): string {
  if (kind === 'invoice') return `invoice ${str(ref)}`
  if (kind === 'rent') return `rent for lease ${str(ref)}`
  if (kind === 'purchase_order') return `a purchase order${args?.qty ? ` (${str(args.qty)} × ${str(args.sku)})` : ''}`
  return `${str(kind).replace(/_/g, ' ')} ${str(ref)}`.trim()
}

/** What an agent just did, as a short sentence. */
export function describeCall(tool: string, a: Record<string, unknown>): string {
  switch (tool) {
    case 'get_ticket': return `Read ticket ${str(a.ticket_id)}`
    case 'list_tickets': return 'Looked at the whole board'
    case 'check_stock': return `Checked stock of ${str(a.sku)}, size ${str(a.size)}${a.qty_needed ? ` (needs ${str(a.qty_needed)})` : ''}`
    case 'list_inventory': return a.sku ? `Looked at stock of ${str(a.sku)}` : 'Looked at all the stock'
    case 'check_margin': return `Checked the margin on ${str(a.sku)} at ${money(num(a.offered_unit_price))} each`
    case 'get_pricing': return a.sku ? `Looked up the price of ${str(a.sku)}` : 'Looked up the prices'
    case 'list_vendors': return 'Looked at the vendors'
    case 'list_invoices': return 'Looked at the invoices'
    case 'list_leases': return 'Looked at the leases'
    case 'check_cash': return 'Checked the cash'
    case 'list_approvals': return 'Looked at the payment approvals'
    case 'list_drafts': return 'Looked at the saved drafts'
    case 'list_payments': return 'Looked at the payments made'
    case 'request_payment_approval': return `Asked for a person to approve paying ${paymentFor(a.kind, a.ref_id, a)}`
    case 'draft_customer_message': return `Saved a draft message for ticket ${str(a.ticket_id)}`
    case 'update_ticket': return `Set ticket ${str(a.ticket_id)} to ${statusWords(a.status)}`
    default: return tool.replace(/_/g, ' ')
  }
}

/** What came back, as a short sentence. Returns null for a tool it has no wording for. */
export function describeResult(tool: string, r: Record<string, unknown>): string | null {
  switch (tool) {
    case 'get_ticket': {
      const t = (r.ticket ?? {}) as Record<string, unknown>, inv = r.invoice as Record<string, unknown> | null
      const invoice = inv ? ` Invoice ${str(inv.id)} is ${inv.status === 'paid' ? 'paid' : inv.overdue ? 'unpaid and overdue' : 'unpaid'}.` : ''
      return `Ticket ${str(t.id)}: ${str(t.subject)} for ${str(t.requester)}, ${statusWords(t.status)}.${invoice}`
    }
    case 'check_stock':
      return `${str(r.sku)} size ${str(r.size)}: ${num(r.qty)} in stock${num(r.shortfall) > 0 ? `, ${num(r.shortfall)} short` : ''}.`
    case 'list_inventory': {
      const items = list(r.items), out = items.filter((i) => i.out_of_stock).length
      return `${plural(items.length, 'stock line')}${out ? `, ${out} out of stock` : ''}.`
    }
    case 'check_margin':
      return `At ${money(num(r.offered_unit_price))} each the margin is ${money(num(r.margin_per_unit))} a unit (${num(r.margin_pct)}%), ${num(r.discount_pct_off_list)}% off list${r.below_cost ? ', which is below cost' : ''}.`
    case 'get_pricing': {
      const p = list(r.pricing)
      return p.length === 1 ? `${str(p[0].sku)}: costs ${money(num(p[0].unit_cost))}, lists at ${money(num(p[0].list_price))}.` : `${plural(p.length, 'price')} looked up.`
    }
    case 'list_vendors': {
      const v = list(r.vendors), ships = v.filter((x) => x.will_ship).length, blocked = v.length - ships
      return `${plural(v.length, 'vendor')}: ${ships} can ship now${blocked ? `, ${blocked} blocked by an unpaid invoice` : ''}.`
    }
    case 'list_invoices': {
      const i = list(r.invoices), unpaid = i.filter((x) => x.status !== 'paid').length
      return `${plural(i.length, 'invoice')}, ${unpaid} unpaid.`
    }
    case 'list_leases': {
      const l = list(r.leases)
      return l.length ? `${plural(l.length, 'lease')}; lease ${str(l[0].id)} rent is ${money(num(l[0].monthly_rent))}, due ${str(l[0].next_due)}.` : 'No leases.'
    }
    case 'check_cash': {
      const a = list(r.accounts)[0]
      return a ? `Checking has ${money(num(a.balance))}; ${money(num(a.pending_approvals_total))} is waiting for approval, ${money(num(a.balance_after_pending))} is free.` : 'No cash account.'
    }
    case 'list_approvals': {
      const a = list(r.approvals), pending = a.filter((x) => x.status === 'pending').length
      return `${plural(a.length, 'payment approval')}${pending ? `, ${pending} waiting for a person` : ''}.`
    }
    case 'list_drafts': return `${plural(list(r.drafts).length, 'saved draft')}.`
    case 'list_payments': {
      const p = list(r.payments)
      return `${plural(p.length, 'payment')} made${p.length ? `, ${money(p.reduce((s, x) => s + num(x.amount), 0))} in all` : ''}.`
    }
    case 'list_tickets': return `${plural(list(r.tickets).length, 'ticket')} on the board.`
    case 'request_payment_approval':
      return `Prepared approval ${str(r.approval_id)}: ${paymentFor(r.kind, r.ref_id)}, ${money(num(r.amount))}, waiting for a person. No money has moved.`
    case 'draft_customer_message': return `Draft ${str(r.draft_id)} saved. It was not sent.`
    case 'update_ticket': return `Ticket ${str(r.ticket_id)} is now ${statusWords(r.status)}.`
    default: return null
  }
}

/** The tool as a noun phrase, for "... was refused". */
const NOUNS: Record<string, string> = {
  get_ticket: 'Reading the ticket', list_tickets: 'Looking at the board', check_stock: 'Checking the stock',
  list_inventory: 'Looking at the stock', check_margin: 'Checking the margin', get_pricing: 'Looking up the price',
  list_vendors: 'Looking at the vendors', list_invoices: 'Looking at the invoices', list_leases: 'Looking at the leases',
  check_cash: 'Checking the cash', list_approvals: 'Looking at the approvals', list_drafts: 'Looking at the drafts',
  list_payments: 'Looking at the payments', request_payment_approval: 'Preparing the payment',
  draft_customer_message: 'Saving the draft', update_ticket: 'Updating the ticket',
}
const toolNoun = (tool: string): string => NOUNS[tool] ?? tool.replace(/_/g, ' ')

/** A tool as a short action, for the small chips on the cards. */
const LABELS: Record<string, string> = {
  get_ticket: 'Read ticket', list_tickets: 'See the board', check_stock: 'Check stock', list_inventory: 'See all stock',
  check_margin: 'Check margin', get_pricing: 'Look up prices', list_vendors: 'See vendors', list_invoices: 'See invoices',
  list_leases: 'See leases', check_cash: 'Check cash', list_approvals: 'See approvals', list_drafts: 'See drafts',
  list_payments: 'See payments', request_payment_approval: 'Prepare payment', draft_customer_message: 'Save draft',
  update_ticket: 'Update ticket',
}
export const toolLabel = (tool: string): string => {
  const callee = calleeOf(tool)
  return callee ? `Ask ${agentLabel(callee)}` : (LABELS[tool] ?? tool.replace(/_/g, ' '))
}

// ---------------------------------------------------------------- the activity feed

export type FeedKind = 'start' | 'asks' | 'uses' | 'says' | 'result' | 'reply' | 'refused' | 'end' | 'error' | 'human'

export interface FeedItem {
  key: string
  agent: string | null
  depth: number
  kind: FeedKind
  text: string
  tool?: string
  json?: string // raw JSON shown in its own monospace block (only when there are no words for it)
  inv?: string | null // which turn of the agent this line belongs to
  time: string
}

export function feedItems(events: AgentEvent[]): FeedItem[] {
  const out: FeedItem[] = []
  for (const e of events) {
    const base = { agent: e.agent, depth: e.depth, time: e.time }
    const push = (i: number, kind: FeedKind, text: string, tool?: string, json?: string) =>
      out.push({ ...base, key: `${e.id}-${i}`, kind, text: plain(text), tool, json, inv: e.invocation })
    const d = e.detail
    switch (e.event) {
      case 'agent_start': {
        const by = d.asked_by ? agentLabel(d.asked_by as string) : 'the board'
        push(0, 'start', `Got a request from ${by}: ${String(d.prompt ?? '')}`)
        break
      }
      case 'model_response': {
        textOf(e).forEach((t, i) => push(i, 'says', t))
        toolCalls(e).forEach((c, i) => {
          const callee = calleeOf(c.tool)
          if (callee) push(10 + i, 'asks', `Asks ${agentLabel(callee)}: ${str(c.args.request)}`, c.tool)
          else if (c.tool === 'final_result')
            push(10 + i, 'says', `Reports: ${reportText(c.args) ?? brief(c.args, 260)}`, c.tool)
          else push(10 + i, 'uses', describeCall(c.tool, c.args), c.tool)
        })
        break
      }
      case 'tool_result': {
        const tool = d.tool as string
        if (tool === 'final_result') break
        const callee = calleeOf(tool)
        if (callee) {
          push(0, 'reply', `${agentLabel(callee)} answered: ${reportText(d.result) ?? brief(d.result, 260)}`, tool)
        } else if (d.result && typeof d.result === 'object' && (d.result as { ok?: boolean }).ok === false) {
          push(0, 'refused', `${toolNoun(tool)} was refused: ${(d.result as { error?: string }).error ?? 'no reason given'}`, tool)
        } else if (d.result && typeof d.result === 'object') {
          const words = describeResult(tool, d.result as Record<string, unknown>)
          if (words) push(0, 'result', words, tool)
          else push(0, 'result', `${toolNoun(tool)} came back with:`, tool, brief(d.result, 240))
        } else {
          push(0, 'result', `${tool} returned ${brief(d.result, 150)}`, tool)
        }
        break
      }
      case 'tool_retry':
        push(0, 'refused', `${toolNoun(d.tool as string)} had to be tried again: ${brief(d.problem, 160)}`, d.tool as string)
        break
      case 'agent_end': {
        const o = d.output as Record<string, unknown> | undefined
        push(0, 'end', `Finished: ${(o?.summary as string) ?? (o?.decision as string) ?? 'done'}`)
        break
      }
      case 'error':
        push(0, 'error', `Error: ${d.message as string}`)
        break
      case 'human_action':
        push(0, 'human', ((d.summary as string) ?? 'Human action').replace(/purchase_order/g, 'purchase order'))
        break
      default:
        break // run_start / run_end are shown by the run banner instead
    }
  }
  // An agent's last model step reports its answer and its turn then finishes with the same words. Keep the one line.
  const finished = new Set(out.filter((i) => i.kind === 'end').map((i) => `${i.agent}|${i.inv}|${i.text.replace(/^Finished: /, '')}`))
  return out.filter((i) => !(i.kind === 'says' && i.tool === 'final_result' && finished.has(`${i.agent}|${i.inv}|${i.text.replace(/^Reports: /, '')}`)))
}

// ---------------------------------------------------------------- one run, one agent

export const latestRunId = (events: AgentEvent[]): string | null =>
  events.length ? events[events.length - 1].run_id : null

export type AgentState = 'idle' | 'working' | 'done'

export interface AgentView {
  name: AgentName
  state: AgentState
  turns: number
  doing: string
  said: string | null
  tools: string[]
}

function doingNow(last: AgentEvent | undefined): string {
  if (!last) return 'waiting to be asked'
  switch (last.event) {
    case 'agent_start':
      return 'reading the request'
    case 'model_response': {
      const c = toolCalls(last)[0]
      if (!c) return 'thinking'
      const callee = calleeOf(c.tool)
      if (callee) return `asking ${agentLabel(callee)}`
      return c.tool === 'final_result' ? 'writing its report' : toolNoun(c.tool).toLowerCase()
    }
    case 'tool_result': {
      const tool = last.detail.tool as string
      const callee = calleeOf(tool)
      return callee ? `${agentLabel(callee)} answered` : 'reading what came back'
    }
    case 'tool_retry':
      return 'retrying a tool call'
    case 'agent_end':
      return 'finished'
    case 'error':
      return 'hit an error'
    default:
      return 'working'
  }
}

export function agentView(runEvents: AgentEvent[], name: AgentName): AgentView {
  const mine = runEvents.filter((e) => e.agent === name)
  const starts = mine.filter((e) => e.event === 'agent_start').length
  const ended = mine.filter((e) => e.event === 'agent_end' || e.event === 'error').length
  const state: AgentState = starts === 0 ? 'idle' : starts > ended ? 'working' : 'done'
  let said: string | null = null
  const tools: string[] = []
  for (const e of mine) {
    if (e.event === 'model_response') {
      const t = textOf(e).join(' ')
      if (t) said = t
      for (const c of toolCalls(e)) {
        const callee = calleeOf(c.tool)
        if (callee) said = `To ${agentLabel(callee)}: ${str(c.args.request)}`
        if (c.tool !== 'final_result' && !tools.includes(c.tool)) tools.push(c.tool)
      }
    } else if (e.event === 'agent_end' && e.said) said = e.said
  }
  return { name, state, turns: starts, doing: state === 'done' ? 'finished' : doingNow(mine[mine.length - 1]), said: said ? plain(said) : said, tools }
}

// ---------------------------------------------------------------- summaries and outcome

export interface AgentSummary {
  invocation: string
  report: AgentReport | null
  decision: TicketDecision | null
}

export function summariesFor(runEvents: AgentEvent[], name: AgentName): AgentSummary[] {
  return runEvents
    .filter((e) => e.agent === name && e.event === 'agent_end')
    .map((e) => {
      const o = e.detail.output as Record<string, unknown> | undefined
      const isDecision = o !== undefined && 'decision' in o && 'owners' in o
      return {
        invocation: e.invocation ?? name,
        report: o && !isDecision ? (o as unknown as AgentReport) : null,
        decision: o && isDecision ? (o as unknown as TicketDecision) : null,
      }
    })
}

export type RunState = 'none' | 'running' | 'finished' | 'failed' | 'interrupted'

export interface RunOutcome {
  state: RunState
  decision: TicketDecision | null
  startedAt: string | null
  tokens: number | null
}

export function runOutcome(runEvents: AgentEvent[], backendSaysRunning: boolean): RunOutcome {
  const start = runEvents.find((e) => e.event === 'run_start')
  const end = runEvents.find((e) => e.event === 'run_end')
  const startedAt = start?.time ?? runEvents[0]?.time ?? null
  if (!runEvents.length) return { state: backendSaysRunning ? 'running' : 'none', decision: null, startedAt, tokens: null }
  if (end) {
    const usage = end.detail.usage as { input_tokens?: number; output_tokens?: number } | undefined
    return {
      state: end.detail.status === 'finished' ? 'finished' : 'failed',
      decision: (end.detail.decision as TicketDecision | undefined) ?? null,
      startedAt,
      tokens: usage ? (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0) : null,
    }
  }
  return { state: backendSaysRunning ? 'running' : 'interrupted', decision: null, startedAt, tokens: null }
}

// ---------------------------------------------------------------- tickets and approvals

export const statusLabel = (t: Ticket): string => {
  if (t.state === 'resolved') return 'RESOLVED'
  switch (t.status) {
    case 'waiting_approval':
      return 'WAITING FOR A HUMAN'
    case 'in_progress':
      return 'IN PROGRESS'
    default:
      return 'OPEN'
  }
}

export function approvalTitle(a: Approval): string {
  switch (a.kind) {
    case 'invoice':
      return `Pay vendor invoice #${a.ref_id}`
    case 'rent':
      return `Pay rent, lease ${a.ref_id}`
    case 'purchase_order':
      return `Purchase order, vendor ${a.ref_id}`
    default:
      return `${a.kind} ${a.ref_id}`
  }
}
