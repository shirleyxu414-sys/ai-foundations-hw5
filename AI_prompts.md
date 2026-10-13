# AI Prompts Log

One section per problem. Each section has the problem number/title, the prompts I sent, and any follow-up prompt I needed. The working site, the saved database changes, and screenshots are the proof of work — no extra essay beyond the prompts.

## Setup / Background

- today we are working on hw 5
- no, don't do anything until i give you the instructions
- show the hw 5 folder in the files tab
- show it here (with a screenshot of the Files tab still showing the lecture 7 files)
- create a joke there to demonstrate you know which folder we are working on
- To give you some background information first. We are going to finish a Campus Customs Multi-agent operations. It is the agentic team that runs the shop.
- Work comes in as tickets on a shared board: customer orders, rent, unpaid bills, discount requests, anything the shop must handle. You will build three connected parts: an MCP server, a FastAPI backend that hosts the multi-agent team, and a React dashboard that lets a human watch the agents work and approve their requests.
- The agent team has full connectivity, so any agent can delegate tasks to any other agent. You will build these agents:  
  - Boss: triages each ticket, assigns owners, and makes the final decision  
  - Inventory: checks stock by SKU and size, flags shortfalls, and finds the vendor to restock  
  - Accounting: tracks cash and invoices, checks margins, and prepares payments or purchase orders for human approval  
  - Facilities: manages the shop space, including leases and rent  
  - Customer Service: drafts customer-facing messages
- This is just background information, do not start until I give you instructions
- Can you see the data/campus_customs.db file now?
- This is the original shop database. Tables include desk, tickets, inventory, pricing, vendors, leases, cash_accounts, payments, and invoices. Can you check first?
- Your tools will update the database as tickets get resolved. Make a copy of the database file called data/campus_customs_new.db and point your MCP server and backend to the working copy. Keep campus_customs.db untouched so you can reset when you need to restart resolving tickets.
- There are rules of this shop, see below:  
  - The field `desk.date_today` is "today" for the shop. Use it to decide what is overdue.  
  - Vendor lead times come from the `vendors` table.  
  - A vendor will not ship new product while an invoice to them is still unpaid.  
  - Every payment needs human approval. Points are deducted if this is skipped. Once a payment is made, update the relevant table.  
  - If there is not enough cash, the pay tool must refuse. Balances never go negative.  
  - In this homework cash only goes out. Revenue is not modeled, so no money comes in.  
  - Before a full run to resolve the tickets, reset the database to its original values.  
  - Do not email customers or call real vendors. Drafts stay on the board.
- Use my PORTKEY_API_KEY for AI calls. For this assignment, every agent uses only gpt-6-luna through Portkey.

## Problem 1: Vibe coder prompts

- Now let's work on Problem 1: Vibe coder prompts. Create AI_prompts.md, which I saw you already did, and keep updating it as you work. This is the log of what I typed to you.
- Put one section for each problem. Each section must include: Problem number and title. Prompts I typed. Follow-up prompt if any.

## Problem 2: Study the Campus Customs database

- Problem 2: Study the Campus Customs database. Open data/campus_customs.db and look at every table and field. Copy the original file to data/campus_customs_new.db, and update later problems in that working copy. Learn the three open tickets so you will see how they link to other tables.
- Now create output/harness.md. List the fields for each table and one short line on why that table matters for the agents. You need to grow this harness file in later problems.

## Problem 3: Build the MCP server

- Problem 3: Build the MCP server. Write an MCP server in mcp_server/ using FastMCP. This server talks to the database at data/campus_customs_new.db. For this problem you do not need to connect to it or run it.
- Every agent in this homework uses the tools in this MCP server. More tools will be added later. For now, write three tools that you know the tickets in the database will need. Use clear tool names. Never make up data. Use only what is in the database.
- In output/harness.md and list all three MCP tools there. For each tool, write which table it reads, which ticket it unlocks (101, 102, or 103), and one sentence explaining why that tool fits that ticket. Vague lines like "reads inventory" will score low. Tie each tool to its ticket. Also write a short mcp_server/README.md that explains what the MCP server is for, which database file it uses, and the three tools it contains.

## Problem 4: Add the MCP server to vibe coder and test each tool

- Problem 4: Add the MCP server to vibe coder and test each tool. Add the MCP server to this project so you can call your tools. Save the connection JSON in .mcp.json at the project root, or wherever you keep your local MCP server list.
- Is the vibe coder connected?
- Can you connect it?
- Why are you looking at lecture 7? Just use what's in hw 5.
- Add the MCP server to this project so the vibe coder can call the tools. Save the connection JSON in .mcp.json at the project root, or wherever the vibe coder keeps your local MCP server list. Is this done?
- Test each of your 3 MCP tools. Save evidence in output/mcp_smoke.json. For every tool, include: the prompt you gave the vibe coder; the tool name; the tool output (values must match `data/campus_customs_new.db`)
- What do you mean by opening a new session?
- I thought we are working on a new session for hm 5 instead starting with lecture 7.
- Let's work on hw 5 today.
- You asked me to start a new session. Is it done now?
- Let's change the working folder into hw 5.
- Is the vibe coder now connected?
- Yes. (run the smoke tests live through the connected tools)
- Check from the beginning to problem 4. Is everything correctly done?
- We can use gpt-6-luna.

## Problem 5: Build the agent team and grow the MCP tools

- Problem 5: Build the agent team and grow the MCP tools. Build the agentic team for Campus Customs with PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service. Write the prompts, models, and agent loops so the agents can delegate work to each other with full connectivity.
- Put the agent prompts in backend/prompts/ with one file per agent. Put data types in backend/models.py and the agent files under backend/. Your layout can vary as long as the five roles stay clear. Use your PORTKEY_API_KEY and only gpt-6-luna for every agent.
- Now I am building the Campus Customs agent team. Next I will paste five agent prompts, one at a time. Each one is the full system prompt for one agent: Boss, Inventory, Accounting, Facilities, and Customer Service. Save each one in a separate file under backend/prompts/ with these names: boss.md, inventory.md, accounting.md, facilities.md, customer_service.md. You can make suggestions, but you need my approval. Tell me when you are ready for the first one.
- You are Boss, the lead agent for Campus Customs. You look at every ticket on the board and make the final decision.

  What you read:  
  - The ticket board, which lists every open ticket including 101, 102, and 103  
  - The desk table, to find today's date  
  - Any other table when a decision needs more facts

  What you decide:  
  - Which agent takes each ticket  
  - Which tickets come first  
  - The final answer when two agents disagree

  What you delegate:  
  - Stock and vendor questions go to Inventory  
  - Money, invoices, and payments go to Accounting  
  - Rent and lease questions go to Facilities  
  - Messages to customers go to Customer Service  
  - Never do a specialist agent's job yourself

  Rules you must follow:  
  - desk.date_today is today for the shop. Use it to decide what is late.  
  - Every payment needs a human to approve it. You show payment requests to the human and never approve them yourself.

  Things you must never do:  
  - Never approve or make a payment  
  - Never make up data. Use only what is in the database.  
  - Never email customers or call vendors. Every message stays as a draft on the board.
- OK with your suggestions.
- You are Inventory. You check what is in stock and find a vendor to fill it back up.

  What you read:  
  - The inventory table, by SKU and size  
  - The vendors table for lead times

  What you decide:  
  - Which items are low or out of stock  
  - Which vendor can restock and how long it takes

  What you delegate:  
  - If a vendor has an unpaid invoice, tell Accounting. That vendor will not ship until it is paid.  
  - If no vendor can restock in time, tell Boss.

  Rules you must follow:  
  - Vendor lead times come from the vendors table.  
  - A vendor will not ship new product while an invoice to them is still unpaid.

  Things you must never do:  
  - Never make up stock numbers.  
  - Never pay a vendor yourself.
- ok
- You are Accounting. You watch the cash and the invoices and get payments ready.

  What you read:  
  - The cash table for how much money is left  
  - The invoices table for what is owed  
  - Cost and price data when you check profit

  What you decide:  
  - Profit on orders  
  - How much a payment should be  
  - Which payments and purchase orders to draft

  What you delegate:  
  - Payment and purchase order drafts go to Boss for a human to approve  
  - If there is not enough cash, tell Boss

  Rules you must follow:  
  - Every payment needs a human to approve it. Never pay without approval.  
  - If there is not enough cash, the pay tool must refuse. Balances never go below zero.  
  - In this homework cash only goes out. No money comes in.

  Things you must never do:  
  - Never pay without a human approving it.  
  - After a payment is made, update the right table.
- Ok.
- You are Facilities. You look after the shop space, the leases, and the rent.

  What you read:  
  - The leases table  
  - The rent schedule

  What you decide:  
  - Which rent is due or late  
  - Shop space problems

  What you delegate:  
  - Late rent goes to Accounting to get the payment ready  
  - Lease problems go to Boss

  Rules you must follow:  
  - Use desk.date_today to decide what is late.  
  - You do not pay rent yourself. Accounting gets the payment ready and a human approves it.

  Things you must never do:  
  - Never pay rent yourself  
  - Never make up lease terms
- Ok.
- You are Customer Service. You write messages to customers.

  What you read:  
  - Orders and customer details  
  - Discount requests

  What you decide:  
  - Drafts of messages to customers

  What you delegate:  
  - Before you promise a restock date, ask Inventory  
  - Discounts and promises go to Boss for approval

  Rules you must follow:  
  - Drafts stay on the board. Do not email customers or call vendors.

  Things you must never do:  
  - Never send a real message. Drafts only.  
  - Never make up stock, price, or delivery data.
- Ok.
- Add any tools the agents need to your MCP server so they can work on the open tickets. All shop facts come from the MCP server through data/campus_customs_new.db. Do not build a second shop-tools layer that skips MCP.
- Make the agents append to output/audit_trail.json while they run. For each agent-loop step, record enough detail to audit later. Keep adding to this file. Do not wipe it at the start of each run.
- In output/harness.md, list every agent and every MCP tool (including the ones you add in this problem) with the table each tool reads. Then write a short safety section. Cover two things: the guardrails a real business would want when agents handle real customers and real money, and the limits that keep token use under control.
- Update mcp_server/README.md so the tool list matches the tools you have now.

## Problem 6: Plan the three tickets

- Problem 6: Plan the three tickets  
  Before you wire the backend, write what you expect the team to do for each open ticket. Build output/desk_tickets.html, a page you can open by double-clicking, with one tab for each ticket (101, 102, and 103).
- Also add empty Cash and Reflection tabs for later problems. Leave them blank or add a short "coming later" note.  
  On each ticket tab, fill in the Expected section only. Leave room for an Actual section that you will fill in after the agents run.

- For each ticket's Expected section:

  Ticket 101 · Bulldog tee  
  1. Who Boss calls first: Inventory, because this is a stock problem. First check stock and find the vendor.  
  2. Agent Delegation:  
  Boss calls Inventory to check stock and find the vendor.  
  Inventory tells Accounting: the vendor is blocked by unpaid invoice 501, so Accounting prepares that payment.  
  Boss calls Customer Service to write a draft to the customer.  
  Back to Boss to set the final status.  
  3. Tools: MCP tools you expect that run to use.

  Ticket 102 · Rent due  
  1. Who Boss calls first: Facilities, because rent is a space and lease issue. No stock and no customer involved.  
  2. Agent delegation:  
  Boss calls Facilities to read the lease and confirm the amount and due date.  
  Facilities tells Accounting to prepare the rent payment for a human to approve.  
  Back to Boss to set the final status.  
  3. Tools: MCP tools you expect that run to use.

  Ticket 103 · Bulk hoodie discount  
  1. Who Boss calls first: Inventory, because they want 20 hoodies but stock may be short, so check stock first.  
  2. Agent delegation:  
  Boss calls Inventory to check stock and find the vendor for the shortfall.  
  Inventory tells Accounting: the vendor is blocked by invoice 501.  
  Boss calls Accounting to check margin at a few prices and check cash.  
  Boss decides the discount price.  
  Boss calls Customer Service to write a draft, only after Boss confirms the discount.  
  Back to Boss to set the final status.  
  3. Tools: MCP tools you expect that run to use.

  Plans that send every specialist on every ticket score low. You will compare this plan to what actually happens when your agents resolve the three tickets.

  You can improve my thoughts if necessary but tell me what should be improved.


## Problem 7: Backend routes

- Now work on Problem 7: Backend routes.  
  The next problem builds a React dashboard, and that dashboard needs something on the server to call. Set up backend/main.py with FastAPI, and add routes that do the following:  
  * Return the three tickets and whether each one is open or resolved  
  * Take a ticket id and run the agent team on that ticket  
  * Return the recent agent events, meaning what each agent said and which tools each one used, so the board can refresh  
  * Approve a payment or purchase after a human clicks approve. Agents only prepare the payment. This route is the one that actually moves the cash.  
  * Return the current checking balance from `cash_accounts`  
  * Reset the database to its original values when you want a fresh run
- From the backend/ folder, start the server with:  
  uvicorn main:app --reload --port 8000  
  This starts your backend at http://localhost:8000 so the frontend dashboard can call those routes.  
  In output/harness.md, list every route in one line, with its URL and what it does.

## Problem 8: Frontend dashboard

- Build the frontend dashboard in frontend/ using React + Vite + TypeScript. The page should call the routes you built in Problem 7. At minimum, the board should:  
  * List all three tickets  
  * Let you pick one ticket and start the agent team on it  
  * Show each agent and what it is saying and doing while the ticket runs  
  * Mark a ticket resolved when the run finishes  
  * Show a short summary of what each agent did on that ticket  
  * Let a human approve a payment or purchase when asked  
  * Show the checking balance. It should drop after an approved payment.
- Restyle output/desk_tickets.html into a warm, calm paper desk look. Keep all the text, data, tabs, and JavaScript exactly as they are. Change only the visuals.

  Direction:  
  - Warm cream page background, like paper on a wooden desk  
  - White cards with a thin soft border and a very soft shadow  
  - Dark ink text on light paper, with muted brown for captions  
  - One accent color for small highlights: a deep red stamp color  
  - Status colors: blue for open, amber for waiting approval, green for resolved, red for errors  
  - Headings in a serif font, body text in the current sans serif, keep monospace for ids and code

  Remove:  
  - The black background and the neon pink everywhere  
  - The dark skyline banner at the top  
  - All glow and text shadow effects  
  - The hard offset shadows and the angled tab corners. Use simple rounded tabs instead

  Keep:  
  - The five tabs and their labels  
  - The Expected and Actual layout  
  - Every stat, table, and flow list  
  - The exact wording of every label

  Do not change any text, data value, or JavaScript behavior. Visual restyle only.
- Make the dashboard look good. This is a real desk people would want to sit at.
- Point the front end at your backend at http://localhost:8000. On the backend, allow the Vite page origin, usually http://localhost:5173, so the browser can call those routes.
- Start the board with:  
  npm run dev  
  This opens the React desk in your browser, where you can pick tickets and watch the agents.  
  Write output/design.md explaining the look you chose for the dashboard. Cover the layout, how each agent is shown differently, and how resolved tickets and cash appear, plus why you made these choices. Include the creative choices that make it feel special and pleasant to use.
- Fix five issues on the agent cards. Do not change any data or logic.

  1. Rename the DOING label to STATUS, or only show DOING while the agent is running. "finished" should never appear next to a label that says DOING.  
  2. Remove the native browser tooltip on the cards. If you keep a hint, show it as a small line of text under the cards, styled to match the page.  
  3. Move the DONE and IDLE badges fully inside each card, aligned right on the same row as the agent name.  
  4. Make the left color bar the same width on all five cards. Keep the per-agent colors, but none of them should look thicker or louder than the others.  
  5. Make all five cards the same height. Center the second row if there is an empty slot. Give the tool chips area a fixed minimum height so cards align even when a card has no chips.
- Give me the link
- I can't open the dashboard
- Fix four more things on the dashboard.

  1. Remove the L1 to L6 number chips from the section headers. Keep only the plain titles, like "Tickets on the board" and "The agent team". Do not touch any code that uses those labels internally.

  2. In Live activity, reset the agent filter back to "everyone" whenever a new ticket run starts or a different ticket is selected. Facilities should not stay selected after the run ends.

  3. On the Customer Service card, move the DONE badge fully inside the card, aligned right on the name row.

  4. In "What each agent did", show all five agents. For agents that did not work on the ticket, show a lighter card that says "Did not work on this ticket". Also shorten the text on the agent team cards to one short line, and keep the full story in the "What each agent did" section.
- When I clicked, there was no response. And include these dashboard related prompts into AI_prompts.md.
- Fix the layout of the agent team cards.

  1. Use a grid that fits all five cards, for example three columns with the last row left aligned. Do not center a single leftover card below the others.

  2. Style the selected card with a soft highlight, like a light background tint or a thin accent border. Do not use a thick black border.

  3. Make all cards the same height per row, and let the chips and text fill the space. Avoid one card stretching with a large empty area.

  4. Give the SAID text two to three lines before truncating. If it is longer, let the card grow or scroll instead of cutting it to one line.
- Improve the dashboard.

  1. In Live activity, do not log a "Reports" event when its text is identical to the "Finished" event of the same agent at the same time. Keep one.

  2. In "What each agent did", use three columns per row with the last row left aligned, so no single card floats alone.

  3. In "Needs a human", add a total line under the approved items, like "Total approved: $3,256.00".

  4. In the checking balance card, add one small line showing the starting balance after reset.

  5. Make the "Run the team again" button state clear: normal accent color when clickable, dimmed with a short reason when not.

  6. Show raw JSON lines in Live activity in monospace on a light background block, distinct from normal sentences.
- What is being blocked?
- I approved already
- There are codes instead of words
- I think after my human approval, it should keep running instead of stopping here, right?

## Problem 9: Resolve the tickets

- Problem 9: Resolve the tickets.  
  Before you test the agents on a full run over the three tickets, reset the working database data/campus_customs_new.db again so you start clean. Write down the starting checking balance. Then run all three tickets on the board (101, 102, 103) until each one is resolved.

- Go back to output/desk_tickets.html from Problem 6. On each ticket tab, fill in the Actual section based on this run. Record which agents took part, what each one handed off, and which tools they called. Leave the Expected section as it is, so you can compare the two side by side.
- On the Cash tab of the same output/desk_tickets.html, list the money item by item:

  * The starting checking balance, right after the reset  
  * For each ticket, how the cash changed when that ticket resolved, and why: which payment or purchase it was, and the dollar amount  
  * The ending checking balance. This number must match `cash_accounts` in the working database.

- Cash math errors lose points, even when the board shows every ticket resolved. Also save these two files:  
  * `output/resolved_tickets.json`: for each ticket, its id, final status, a short outcome, what each agent contributed, and any human approvals  
  * `output/resolved_board.html`: a page you can open by double-clicking, with a screenshot of your React board for each resolved ticket (101, 102, and 103)
- Add the real run records to output/audit_trail.json. Then complete output/harness.md so it covers all of it: the tables, the MCP tools, the five agents, the API routes, the dashboard, and the safety rules.

## Problem 10: Reflection

- Problem 10: Reflection.  
  Go back to output/desk_tickets.html and fill in the Reflection tab. Write the answers in your own voice, and go into detail:

  * How well did the agents do on each ticket? Explain why.  
  * For each ticket, how did what actually happened compare with the Expected plan you wrote earlier?  
  * Which part of this would have been simpler as a single agent with tools? Explain why.  
  * Name three new problems Campus Customs could face that this agent team can solve with the tools you already built  
  * Name three new problems Campus Customs could face that this agent team cannot solve with the tools you built. For each one, explain what tools and agents you would need.
- Tie every answer to this app and the three tickets you ran. Use the ticket tabs and the Cash tab on the same page as your evidence.
