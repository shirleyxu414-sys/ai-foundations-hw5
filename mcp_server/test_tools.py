import asyncio, json
from fastmcp import Client

cfg = json.load(open(".mcp.json"))  # the exact connection saved for the project

async def main():
    async with Client(cfg) as c:
        print("TOOLS:", [t.name for t in await c.list_tools()])
        calls = [
            ("check_stock", {"sku": "CC-TEE-WHITE", "size": "S", "qty_needed": 1}),
            ("check_stock", {"sku": "CC-HOOD-NAVY", "size": "M", "qty_needed": 20}),
            ("check_stock", {"sku": "CC-TEE-WHITE", "size": "XXL"}),
            ("get_ticket", {"ticket_id": 101}),
            ("get_ticket", {"ticket_id": 102}),
            ("get_ticket", {"ticket_id": 103}),
            ("get_ticket", {"ticket_id": 999}),
            ("check_margin", {"sku": "CC-HOOD-NAVY", "offered_unit_price": 50}),
            ("check_margin", {"sku": "CC-HOOD-NAVY", "offered_unit_price": 20}),
            ("check_margin", {"sku": "CC-NOPE", "offered_unit_price": 10}),
        ]
        for name, args in calls:
            r = await c.call_tool(name, args)
            print(f"\n{name} {args}\n", json.dumps(r.data, indent=1))

asyncio.run(main())
