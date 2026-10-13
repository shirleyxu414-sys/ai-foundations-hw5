# Problem 9: Resolve the tickets (run log)

This log describes the **second full run**, the clean rerun I am submitting. The first full run is kept as context at the bottom: it ended at $144.00 after a duplicate $8.00 order, I fixed the causes in my tools, and then reset and ran all three tickets again.

## Start (clean database)

- `data/campus_customs_new.db` was reset to the original values from the dashboard (`POST /api/reset`, which copies `data/campus_customs.db` over it) at **18:30:49 UTC on 2026-10-11**, before any agent ran. A short attempt that began after the 18:15 reset (ticket 101 only, invoice 501 paid) was abandoned by this reset; the automatic backup saved it as `data/backups/campus_customs_new_before_reset_20261011T183049Z.db`.
- **Starting checking balance: $3,400.00** (account `checking`, dated 2026-08-31). The reset reported it, `/api/cash` shows it as `starting_balance`, and the dashboard header says "Started at $3,400.00 after the last reset".
- Payments made: 0. Approvals on the board: 0. Invoice 501: open ($840.00). Lease 1 next due: 2026-09-02. Tickets 101, 102 and 103: all open.

## Result

**All three tickets are resolved.** Ending checking balance: **$152.00**, which matches `cash_accounts`.

| Ticket | Final status | Runs | Model requests | Tokens | Cash out |
|---|---|---|---|---|---|
| 101 Bulldog tee | resolved | 4 | 57 | 173,184 | −$848.00 (payments 1, 2) |
| 102 Rent due | resolved | 2 | 21 | 56,387 | −$2,400.00 (payment 3) |
| 103 Bulk hoodie discount | resolved | 3 (1 failed) | 38 | 119,441 | $0.00 |
| **Total** | | **9 (1 failed)** | **116** | **349,012** | **−$3,248.00** |

Requests and tokens count the finished runs. A failed run records none (ticket 103's second run failed after its model stopped answering; 7 requests had come back before that).

## The money, item by item

| # | Ticket | What | Change | Checking after | Approved by |
|---|---|---|---|---|---|
| start | | right after the reset | | $3,400.00 | |
| 1 | 101 | pay invoice 501 to Bulldog Print Co | −$840.00 | $2,560.00 | Shirley |
| 2 | 101 | purchase order, 1 × CC-TEE-WHITE | −$8.00 | $2,552.00 | Shirley |
| 3 | 102 | pay rent, lease 1, Elm City Properties | −$2,400.00 | $152.00 | Shirley |
| end | | read from `cash_accounts` | | **$152.00** | |

Check: $3,400.00 − $840.00 − $8.00 − $2,400.00 = $152.00. `cash_accounts` says $152.00, and the `payments` table adds up to $3,248.00. There is no duplicate order in this run: the tee was ordered once.

## What happened, in order (UTC, 2026-10-11)

1. **18:30:49** Reset. Starting balance $3,400.00.
2. **18:31:05 to 18:31:12** Ticket 101, pass 1 (7 s). Inventory found the tee out of stock and the vendor blocked by invoice 501; Accounting prepared approval 1 ($840.00); Customer Service saved draft 1. Status `waiting_approval`.
3. **18:31:59** Shirley approved invoice 501 in the dashboard (payment 1, cash $3,400.00 → $2,560.00). The team started pass 2 by itself and Accounting prepared approval 2, an $8.00 purchase order for one tee.
4. **18:32:37** Shirley approved the order (payment 2, $2,552.00). Pass 3 started. **18:32:45** Shirley confirmed the delivery (stock 0 → 1) while pass 3 was running. Pass 3 ended `in_progress` at 18:33:16.
5. **18:33:16 to 18:33:48** Pass 4 (started by the delivery confirmation): Inventory saw 1 on hand, Customer Service saved draft 4, and the Boss resolved ticket 101.
6. **18:33:56 to 18:34:17** Ticket 102, pass 1: Facilities confirmed $2,400.00 due 2026-09-02; Accounting prepared approval 3; a duplicate request from a second Accounting turn was refused by the tool. **18:34:09** Shirley approved the rent (payment 3, $152.00). **18:34:17 to 18:34:34** pass 2 (started by itself) resolved ticket 102. `get_ticket` now says the rent was paid and why the due date moved to 2026-10-02, so there was no "discrepancy".
7. **18:34:43 to 18:37:09** Ticket 103, pass 1 (146 s, two model requests stalled for 30 s each and were retried). Cost $22.00, list $58.00, 8 in stock (short 12). Accounting recommended $46.40. The Boss tried a 12-hoodie order and the tool refused it (not enough cash: $264.00 against $152.00). **18:34:53** Shirley recorded the decision "Offer what we have." ten seconds into this pass, so this pass did not act on it. Status `in_progress`.
8. **18:37:09 to 18:40:05** Pass 2 (started by the decision) **failed**: Customer Service saved two near-identical drafts (7 and 8), then five model requests in a row timed out (30 s each). No status was set.
9. **18:40:33 to 18:41:16** Pass 3 (a new run; a failed run does not restart itself): the Boss followed the decision, offered the 8 hoodies in stock at the $58.00 list price with no discount and no restock, and resolved ticket 103. Draft 9 saved, not sent.

## Human actions (all in `output/audit_trail.json` as `human_action` entries)

- One database reset, at 18:30:49 UTC. It is the one the starting balance is read from.
- Approved payments 1, 2 and 3 in the dashboard (Shirley).
- Confirmed the delivery of purchase order 2 (Shirley).
- Recorded the decision on ticket 103, "Offer what we have." (Shirley).
- No approvals were given in chat in this run.

The database and the audit trail keep each name as it was typed when the action happened ("Shirley Xu" in the dashboard here, "user (approved in chat)" in the first run). Those are history and I do not rewrite them. The generated records (this log, the Cash tab, `resolved_tickets.json`, `resolved_board.html`) show one spelling per person: **Shirley** for the dashboard and **Shirley (in chat)** for chat (`backend/people.py`).

## The first full run, for context (03:01 to 03:48 UTC, 2026-10-11)

| Ticket | Final status | Runs | Model requests | Tokens | Cash out |
|---|---|---|---|---|---|
| 101 Bulldog tee | resolved | 6 | 78 | 220,545 | −$856.00 (payments 1, 3, 4) |
| 102 Rent due | resolved | 4 | 49 | 129,146 | −$2,400.00 (payment 2) |
| 103 Bulk hoodie discount | resolved | 3 | 51 | 141,440 | $0.00 |
| **Total** | | **13** | **178** | **491,131** | **−$3,256.00** |

It ended at $144.00. Payments 1 and 2 (invoice 501 and the rent) were approved in chat (Shirley (in chat)); payments 3 and 4 (two $8.00 tee orders) in the dashboard (Shirley). What went wrong, and what I changed because of it:

- **The shop bought the same tee twice** (payments 3 and 4). Accounting asked for a second $8.00 order because nothing said the first had been paid. A person approved it, and no refund exists (cash only goes out). Fix: `request_payment_approval` now refuses a second request for something already approved and paid on the same ticket.
- **Ticket 102 stuck on a "discrepancy"** for two runs: after the rent was paid, lease 1's due date moved to 2026-10-02, and `get_ticket` did not say why. Fix: `get_ticket` now shows each ticket's approvals, the payment that settled each, and a note explaining the moved due date; approvals link to their exact payment (`payment_id`) so identical orders are never double-counted.
- **Ticket 101 could not resolve** while the tee stayed at 0, because nothing recorded that stock had arrived. Fix: human-only `receive_shipment` ("Mark received" in the dashboard), plus human-only `record_human_decision` for deciding how a ticket ends.
- **Also added after the first run:** auto-continue, a 30 s model timeout and stall logging. After a person approves, declines, receives or decides, the team continues by itself (nothing runs while another approval is pending on that ticket, or if the ticket is resolved).
- Decisions in the first run were recorded in chat ("Shirley (in chat)"): ticket 103 (offer the 8 hoodies at a discount, the Boss chose $45.00 each, 8 × $45.00 = $360.00) and ticket 101 (offer the tee by draft and close it).
- The audit trail's first reset entry (02:51 UTC) came from a dashboard page connected to the real backend and changed nothing; the starting balance is always read from the latest reset.

The two runs are not a controlled comparison: the tools and prompts changed between them, and the model varies from run to run. The rerun used about 70% of the tokens (349,012 against 491,131) and made one order instead of two.

## Keeping both results safe

- `data/backups/after_problem9_final.db` is a byte-for-byte copy of the working database as the first full run ended (3 tickets resolved, 4 payments = $3,256.00, $144.00 in checking). It is identical to `data/backups/campus_customs_new_before_reset_20261011T181503Z.db`.
- The working database `data/campus_customs_new.db` now holds the second, clean run (3 tickets resolved, 3 payments = $3,248.00, $152.00 in checking). Resetting saves a backup to `data/backups/` first, so a rerun cannot silently erase it.
- `backend/refresh_reports.py` rebuilds the Cash tab and the two resolved files from the live data. It reads only the run since the last reset, and refuses to run unless all three tickets are resolved (or `--force`).

## Files

- `output/resolved_tickets.json`: per ticket, status, outcome, what each agent contributed, human approvals, decisions and deliveries, the cash change and run totals.
- `output/resolved_board.html`: double-click to open; a screenshot of the React board for each resolved ticket, with the same facts. Screenshots are in `output/screenshots/`.
- `output/desk_tickets.html`: Expected halves untouched; Actual halves (pass 1, then a table of every pass); the Cash tab; the Reflection.
- `backend/resolved_report.py` and `backend/cash_report.py` rebuild these from the live shop data.
