"""Navigation searches cached metadata only; never connects to a source."""
from urllib.parse import urlencode

from fastapi import APIRouter
from tarsier.storage import connections, item_cache

router = APIRouter()

@router.get("/api/navigation")
def navigation():
    entries = [{"label": "Connections", "url": "/"}, {"label": "Settings", "url": "/settings"}, {"label": "Add connection", "url": "/connections/new"}]
    for saved in connections.list_connections():
        base = f"/connections/{saved.id}"
        for section in ("overview", "statistics", "changes", "alerts", "automations", "flowchart", "graph", "snapshots"):
            entries.append({"label": f"{saved.name} / {section.title()}", "url": f"{base}/{section}"})
        for item in item_cache.list_items(saved.id):
            entries.append({"label": f"{saved.name} / {item.schema + '.' if item.schema else ''}{item.name}", "url": f"{base}/items?{urlencode({'schema': item.schema, 'name': item.name})}"})
    return entries
