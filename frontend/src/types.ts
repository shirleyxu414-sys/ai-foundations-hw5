// Shapes of what the backend (backend/main.py) returns. Kept in step with backend/models.py.

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  status: string // raw board status: open, in_progress, waiting_approval, resolved
  state: 'open' | 'resolved'
  running: boolean
}

export interface TicketDecision {
  ticket_id: number
  status: string
  owners: string[]
  decision: string
  reasoning: string
  approval_ids: number[]
  draft_ids: number[]
}

export interface AgentReport {
  agent: string
  summary: string
  findings: string[]
  actions_taken: string[]
  needs_human_approval: string[]
  blockers: string[]
}

export interface RunStarted {
  run_id: string
  ticket_id: number
  state: 'running'
}

export interface AgentEvent {
  id: number // position in output/audit_trail.json
  run_id: string
  seq: number
  time: string
  ticket_id: number | null
  agent: string | null
  invocation: string | null
  depth: number
  chain: string[]
  step: number | null
  event:
    | 'run_start'
    | 'agent_start'
    | 'model_response'
    | 'model_retry'
    | 'tool_result'
    | 'tool_retry'
    | 'agent_end'
    | 'error'
    | 'run_end'
    | 'human_action'
  said: string | null
  tools: string[]
  detail: Record<string, unknown>
}

export interface EventsPage {
  events: AgentEvent[]
  next_cursor: number
  total: number
}

export interface Cash {
  account: string
  balance: number
  date: string
  pending_approvals_total: number
  balance_after_pending: number
  starting_balance: number | null // what the last reset put in the account; null if no reset is on record
}

export interface Approval {
  id: number
  kind: 'invoice' | 'rent' | 'purchase_order' | string
  ref_id: number
  ticket_id: number | null
  amount: number
  account: string
  reason: string | null
  requested_by: string | null
  status: 'pending' | 'approved' | 'declined' | string
  created_at: string
  sku: string | null
  qty: number | null
  received_at: string | null
  received_by: string | null
}

export interface Received extends Continued {
  ok: boolean
  approval_id: number
  sku: string
  size: string
  qty_received: number
  qty_on_hand_before: number
  qty_on_hand_after: number
}

export interface Continued {
  continued_run_id: string | null // set when this action made the team pick the ticket up again
  continued_ticket_id: number | null
}

export interface Payment extends Continued {
  ok: boolean
  approval_id: number
  kind: string
  ref_id: number
  amount: number
  paid_at: string
  approved_by: string
  balance_after: number
}

export interface ResetResult {
  ok: boolean
  date_today: string
  checking_balance: number
}
