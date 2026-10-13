import asyncio, json, sqlite3
from fastmcp import Client

cfg = json.load(open(".mcp.json"))
db = sqlite3.connect("file:data/campus_customs_new.db?mode=ro", uri=True)
db.row_factory = sqlite3.Row
one = lambda q, *a: dict(db.execute(q, a).fetchone())

CASES = [
    {"ticket": 101,
     "prompt": "Ticket 101: Tauhid Zaman wants a Bulldog tee, size S. Check how many CC-TEE-WHITE size S we have on hand and whether we are short for 1 unit.",
     "tool": "check_stock",
     "arguments": {"sku": "CC-TEE-WHITE", "size": "S", "qty_needed": 1}},
    {"ticket": 102,
     "prompt": "Ticket 102: Elm City Properties says rent is due in 2 days. Read ticket 102, find its lease, and tell me the rent amount and how many days until it is due today.",
     "tool": "get_ticket",
     "arguments": {"ticket_id": 102}},
    {"ticket": 103,
     "prompt": "Ticket 103: Yale AI Club wants a bulk discount on 20 CC-HOOD-NAVY hoodies. Check the margin if we sell at $50 per hoodie.",
     "tool": "check_margin",
     "arguments": {"sku": "CC-HOOD-NAVY", "offered_unit_price": 50}},
]

def expected(c):
    a = c["arguments"]
    if c["tool"] == "check_stock":
        r = one("select * from inventory where sku=? and size=?", a["sku"], a["size"])
        return {"ok": True, **r, "qty_needed": a["qty_needed"], "shortfall": max(0, a["qty_needed"] - r["qty"])}
    if c["tool"] == "get_ticket":
        t = one("select * from tickets where id=?", a["ticket_id"])
        l = one("select * from leases where id=?", t["lease_id"])
        today = one("select date_today from desk")["date_today"]
        from datetime import date
        days = (date.fromisoformat(l["next_due"]) - date.fromisoformat(today)).days
        return {"ok": True, "date_today": today, "ticket": t, "invoice": None, "vendor": None,
                "lease": {**l, "days_until_due": days}}
    p = one("select * from pricing where sku=?", a["sku"])
    m = a["offered_unit_price"] - p["unit_cost"]
    return {"ok": True, "sku": a["sku"], "unit_cost": p["unit_cost"], "list_price": p["list_price"],
            "offered_unit_price": float(a["offered_unit_price"]), "margin_per_unit": round(m, 2),
            "margin_pct": round(100 * m / a["offered_unit_price"], 1),
            "discount_pct_off_list": round(100 * (1 - a["offered_unit_price"] / p["list_price"]), 1),
            "below_cost": m < 0}

async def main():
    results = []
    async with Client(cfg) as c:
        listed = [t.name for t in await c.list_tools()]
        for case in CASES:
            r = await c.call_tool(case["tool"], case["arguments"])
            out = r.data
            exp = expected(case)
            results.append({**case, "output": out, "matches_database": out == exp})
    evidence = {
        "how_this_was_run": "Each call went through the campus-customs MCP server using the exact connection saved in .mcp.json (stdio, FastMCP client). 'prompt' is the request that calls for that tool. 'matches_database' compares the tool output with values read independently from data/campus_customs_new.db with plain SQL.",
        "database": "data/campus_customs_new.db",
        "tools_on_server": listed,
        "results": results,
        "all_match_database": all(x["matches_database"] for x in results),
    }
    json.dump(evidence, open("output/mcp_smoke.json", "w"), indent=2)
    print("tools:", listed, "| all match:", evidence["all_match_database"],
          [x["matches_database"] for x in results])

asyncio.run(main())
