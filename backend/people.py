"""How a person's name is shown in the records.

The database and audit trail keep whatever name was typed when the action happened ("Shirley Xu" in the dashboard,
"user (approved in chat)" for approvals given in chat). Those are history and are never rewritten. The generated
records show one spelling per person: "Shirley" for the dashboard, "Shirley (in chat)" for chat.
"""

CHAT = "Shirley (in chat)"
DASHBOARD = "Shirley"


def display_name(raw: str | None) -> str | None:
    if raw is None:
        return None
    name = raw.strip()
    low = name.lower()
    if low.startswith("user") or "in chat" in low:
        return CHAT
    if low.startswith("shirley"):
        return DASHBOARD
    return name
