# Campus Customs MCP Server

## What it is for

This MCP server (built with FastMCP) is how the Campus Customs agents (Boss, Inventory, Accounting, Facilities, Customer Service) look things up and act on the shop database. Every agent uses the same tools, and every answer comes from the database, never from guesses. It is the only way the agents reach shop data.

## Database file

It uses the working copy `data/campus_customs_new.db` (override with the `CAMPUS_DB` env var). The original `data/campus_customs.db` is never changed; `reset_database()` in `server.py` copies the original over the working copy before a full run. The board tables `approvals`, `drafts` and `ticket_log` are created on first use and are wiped by a reset.

## Tools (21)

Read tools:

| Tool | Table(s) it reads | What it is for |
|---|---|---|
| `get_ticket(ticket_id)` | `tickets`, `invoices`, `vendors`, `leases`, `desk`, `approvals`, `payments`, `ticket_log` | One ticket with its linked invoice, vendor and lease, and days until rent is due. Ticket 102: lease 1 rent ($2,400) due 2026-09-02, checked against today (2026-08-31). |
| `list_tickets(status?)` | `tickets`, `desk` | The whole board, oldest first, with today's date. |
| `check_stock(sku, size, qty_needed?)` | `inventory` | On hand and shortfall for one SKU and size. Ticket 101: tee `CC-TEE-WHITE` size S has 0. |
| `list_inventory(sku?)` | `inventory` | Every size, flagged out of stock (0) or low (3 or fewer). |
| `check_margin(sku, offered_unit_price)` | `pricing` | Margin and discount off list at a proposed price. Ticket 103: a hoodie price must stay above the $22.00 unit cost. |
| `get_pricing(sku?)` | `pricing` | Unit cost, list price and margin at list. |
| `list_vendors()` | `vendors`, `invoices`, `desk` | Specialty, lead days, and whether the vendor will ship (not while an invoice to them is unpaid). |
| `list_invoices(status?)` | `invoices`, `vendors`, `desk` | What we owe, with overdue flags against today. |
| `list_leases()` | `leases`, `desk` | Every lease with days until due and a late flag. |
| `check_cash(account?)` | `cash_accounts`, `approvals` | Balance, pending approvals, and balance after pending. |
| `list_approvals(status?, ticket_id?)` | `approvals` | Payment requests and whether a human has dealt with them. |
| `list_drafts(ticket_id?)` | `drafts` | Customer drafts saved on the board (never sent). |
| `list_payments()` | `payments`, `approvals` | Payments actually made, with the approval and ticket each came from. Empty until a human approves something. |

Write tools (agents can call these):

| Tool | Table(s) it reads | Table(s) it writes |
|---|---|---|
| `request_payment_approval(kind, ref_id, account, reason, ticket_id?, requested_by?, sku?, qty?)` | `invoices`, `leases`, `vendors`, `pricing`, `cash_accounts`, `approvals`, `desk` | `approvals` (a pending request only; no money moves). `kind` is `invoice`, `rent` or `purchase_order`; the amount always comes from the database. |
| `draft_customer_message(ticket_id, message, author?)` | `tickets`, `desk` | `drafts` (never sent) |
| `update_ticket(ticket_id, status, note, author)` | `tickets`, `desk` | `tickets` (status only), `ticket_log` |

Human-only tools (the backend hides these from every agent):

| Tool | Table(s) it reads | Table(s) it writes |
|---|---|---|
| `execute_approved_payment(approval_id, approved_by)` | `approvals`, `cash_accounts`, `invoices`, `leases`, `desk` | `payments`, `cash_accounts`, `invoices` (marked paid) or `leases` (`next_due` + 1 month), `approvals`. Refuses without an approver name or without enough cash. |
| `decline_payment(approval_id, declined_by)` | `approvals` | `approvals` |
| `receive_shipment(approval_id, received_by, size?)` | `approvals`, `tickets`, `inventory`, `desk` | `inventory` (adds the ordered quantity), `approvals`, `ticket_log`. A person confirms a paid purchase order arrived. |
| `record_human_decision(ticket_id, decided_by, decision)` | `tickets`, `desk` | `ticket_log` (as `human:<name>`); agents see it on `get_ticket`. |
| `reset_shop_database()` | the original `campus_customs.db` | replaces `campus_customs_new.db` (also clears `approvals`, `drafts`, `ticket_log`) |

See `output/harness.md` for the full description of each tool and the safety rules.

## Run

```bash
python mcp_server/server.py
```
