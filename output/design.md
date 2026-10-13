# Dashboard design: a paper desk

The dashboard (`frontend/`) is a calm desk you would want to sit at while software spends your money. Cream paper on a wooden desk, white cards with thin soft borders, dark ink, serif headings, and one deep-red "stamp" colour used sparingly. The earlier black-and-pink neon look was replaced everywhere (this board and the ticket plan page) when you asked for the warm paper direction.

## Why this look

Watching agents delegate, read the database and prepare payments could easily feel like an alarm panel. The people using it have one real job: read what the agents did, then decide whether to approve spending. So the design aims for the feel of a tidy desk: quiet surfaces, readable serif headings, lots of white space, and colour that only appears when it means something.

## Layout

- **Top strip:** the title on the left, the **checking balance** in the middle (always visible), and Reset plus the backend connection light on the right. Money is the one thing a human must never lose sight of.
- **Left column, the things you act on:**
  - **Tickets on the board:** three index cards.
  - **Needs a human:** the approvals desk, with the name field and approve buttons.
- **Right column, the stage where the selected ticket plays out, top to bottom:**
  - **The run banner:** the headline and the Run button.
  - **The agent team:** one card per agent in a three-column grid (the last row sits on the left), equal height within each row, with a one-line status and up to three lines of what it said. The selected card is tinted softly in its own color with a thin border.
  - **What each agent did:** the full story for each of the five agents, in three columns with the last row on the left; one that did not work on the ticket gets a lighter card that says so.
  - **Live activity:** the play-by-play feed.
- **Why left/right:** the left is "what is on my desk and what needs me"; the right is "what is happening to the one I picked".
- The page is one screen wide on a laptop and stacks into one column on narrow windows.

## How each agent is shown differently

Each agent has its own name plate with a badge shape, an earth-tone colour and a role line, so you can tell them apart at a glance, even in a long feed, and even if you cannot tell the colours apart (the shapes differ too).

| Agent | Badge | Colour | Idea |
|---|---|---|---|
| Boss | round seal with a ring | stamp red | the one with the final say |
| Inventory | rounded square | cardboard brown | a box on a shelf |
| Accounting | hexagon | ledger slate | a ledger tile |
| Facilities | little house | olive | the space and the lease |
| Customer Service | speech bubble | plum | the voice to customers |

- The same colour runs down the card's left edge, over the agent's name in the activity feed, and on its summary card.
- **State is shown separately from identity:** idle is faded, working has a blue ring and a sweeping blue bar along the top, done gets a green pill. Each card also says what it is doing right now ("asking Accounting", "using check_stock"), what it last said, how many times it was asked, and chips for the tools it used.
- Clicking a card filters the live feed to just that agent.

## Resolved tickets

- A resolved ticket gets a **green left edge, a green ticket number and a green RESOLVED badge** on its card. The banner turns green with a large serif "RESOLVED", and the Run button is disabled with a note.
- **Only the Boss can resolve.** The dashboard never marks a ticket resolved on its own. If a run ends while a payment is waiting, the banner turns amber and says exactly why ("Not resolved yet: 1 payment ($840.00) waiting for a human to approve") and what to do next (approve, then run the team again).
- Colours for status are fixed: **blue = open or working, amber = waiting for a human, green = resolved, red = errors and refusals.** The deep-red stamp colour is never used for status, only for ticket numbers, the small headline above each ticket, the Boss seal and the approve button.

## Cash

- The balance sits in a white card with a large serif figure, like a figure written in a ledger, and a line underneath saying how much is already waiting for approval and what would be left.
- **When a payment goes through, the balance visibly drops:** the card briefly rings in amber and a "−$840.00" chip in red when cash goes out (a green "+" chip when the balance rises, for example after a reset) floats in for a few seconds.
- Approving is deliberate: the approve button is the red stamp, and it takes two clicks (the second is an amber, gently pulsing "Confirm: pay $840.00"). It stays disabled until you have typed your name (the name is saved as the approver) and when the account cannot cover the amount, with a plain sentence saying why.

## Creative choices that make it feel special

- **Index-card tickets** with a coloured edge that tells you the status before you read it.
- **A stamp for approving.** The one saturated colour on the page is on the one action that moves money.
- **Serif headings and ledger-style numerals** on a sans-serif body, so it reads like paperwork, not a console.
- **The feed reads like sentences,** not logs: "Asks Inventory: …", "Accounting answered: …", "check_cash returned …". Delegations are indented by depth so you can see who asked whom, and refusals (for example "not enough cash") stand out in red.
- **Words first, code second:** every tool call and result in Live activity is a plain sentence ("Ticket 101 is now waiting for approval."), the small chips on the cards say what the agent did ("Check stock", "Ask Inventory") instead of showing tool names, and system words like `waiting_approval` or `rent_notice` are shown as ordinary words. The dashboard does not show the raw calls or JSON at all; the full record stays in the audit trail. An agent's last report and its "Finished" line are shown once, not twice.
- **Calm motion only:** a sweeping bar on whoever is working, a soft breathing badge, new lines easing in. Nothing flashes. People who ask their system for reduced motion get a completely still page.
- **Reset keeps the record.** Resetting the database clears the board for a fresh run, but the earlier runs stay in the audit trail, hidden from view rather than deleted.
- **Honest empty and error states:** "Nothing waiting for approval", "Summaries appear here as each agent finishes", and if the backend is down the page says so and shows the exact command to start it.
- **A reassurance line** at the bottom: agents only prepare payments, a human approves, and every step is saved to the audit trail.

## Accessibility

Real buttons for everything clickable, a visible focus ring, live regions on the balance and the feed, text contrast checked against the cream and white surfaces, shapes as well as colours for agents, and reduced-motion support.

## How it was checked

Driven in headless Chrome against the live backend: ticket list, running view, finished view, an approval that dropped the balance from $3,400.00 to $2,560.00 with the drop chip, and reset. Screenshots were reviewed for each state. The two states that could not be reached with real agent behaviour (a ticket the Boss resolves on its own, a run that fails) were checked by setting the status in a scratch database and by a timeout test.
