"""Spatial Knowledge Graph Engine (PRD 14.1, TAD 3: Kuzu, pinned to 0.11.3).

A graph of how sources, layers, tables and rasters relate, richer than the
flowchart's one-hop links: you can ask what is related to an item through
other items (several hops, across connections), the shortest chain between two
items, and which items form a connected group.

Design rules:
- Tarsier's SQLite stays the system of record for connections, items and
  links (TAD 5), including the user's confirm/reject decisions. The Kuzu
  database is a *derived view* rebuilt from SQLite after any change, so it can
  always be thrown away and regenerated, and a corrupted graph never loses user
  decisions.
- Kuzu runs embedded inside this process (no server, no Docker). No Kuzu
  extension is used: the pinned release's optional extension server is gone
  (TAD 3), and shortest-path / variable-length matching are built in.
- If the kuzu package is not importable (it has no wheel for some Python
  versions), the graph reports itself unavailable and nothing else breaks.

Kuzu usage follows the Python API and Cypher forms exercised in the Kuzu
repository's own tests (kuzu-master/tools/python_api/test and
test/test_files/demo_db/demo_db.test, MIT License, (c) Kuzu Inc.): Database /
Connection, parameterised execute(), and `[e* SHORTEST 1..N]` recursive
relationships with an optional `(r, n | WHERE ...)` predicate.
"""

from __future__ import annotations

from tarsier.timing import timed_phase
import shutil
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tarsier.storage import connections as connection_storage
from tarsier.storage import flowchart as flowchart_storage
from tarsier.storage import item_cache
from tarsier.storage.paths import tarsier_home

try:  # pragma: no cover - exercised by the unavailable-path test via monkeypatch
    import kuzu
except ImportError:  # pragma: no cover
    kuzu = None

MAX_HOPS = 6
_lock = threading.Lock()  # one Kuzu Database object per path at a time, per process


class GraphUnavailable(Exception):
    """The graph engine can't run here (Kuzu missing); the message is safe to show."""


def is_available() -> bool:
    return kuzu is not None


def _require() -> None:
    if kuzu is None:
        raise GraphUnavailable(
            "The relationship graph needs the Kuzu library, which isn't available for this Python version. "
            "The rest of Tarsier works without it."
        )


def graph_path() -> Path:
    return tarsier_home() / "graph.kuzu"


def item_key(connection_id: str, schema: str, name: str) -> str:
    return f"{connection_id}|{schema or ''}|{name}"


@contextmanager
def _connection(path: Path | None = None):
    _require()
    with _lock:
        db = kuzu.Database(str(path or graph_path()))
        conn = kuzu.Connection(db)
        try:
            yield conn
        finally:
            conn.close()
            db.close()


def _rows(conn, query: str, params: dict | None = None) -> list[list]:
    result = conn.execute(query, params or {})
    rows = []
    while result.has_next():
        rows.append(result.get_next())
    return rows


def _remove_database_files(path: Path) -> None:
    for sibling in path.parent.glob(path.name + "*"):
        if sibling.is_dir():
            shutil.rmtree(sibling, ignore_errors=True)
        else:
            sibling.unlink(missing_ok=True)


@dataclass(frozen=True)
class GraphStatus:
    available: bool
    built: bool
    sources: int = 0
    items: int = 0
    relations: int = 0
    built_at: str | None = None
    message: str | None = None


_built_at: dict[str, str] = {}


def rebuild_graph() -> GraphStatus:
    """Re-project every connection's items and links from SQLite into Kuzu."""
    _require()
    path = graph_path()
    connections = connection_storage.list_connections()
    items: dict[str, dict] = {}
    for saved in connections:
        for cached in item_cache.list_items(saved.id):
            items[item_key(saved.id, cached.schema, cached.name)] = {
                "connection_id": saved.id, "schema": cached.schema, "name": cached.name,
                "kind": cached.kind, "row_count": cached.row_count if cached.row_count is not None else -1,
            }
    for connection_id, node in flowchart_storage.list_all_nodes():
        items.setdefault(
            item_key(connection_id, node["schema"], node["name"]),
            {"connection_id": connection_id, "schema": node["schema"], "name": node["name"],
             "kind": node["kind"], "row_count": -1},
        )
    known = {saved.id for saved in connections}
    items = {k: v for k, v in items.items() if v["connection_id"] in known}
    # A link's endpoints always exist as items, even before that connection's own scan.
    for link in flowchart_storage.list_all_links():
        for cid, schema, name in (
            (link.connection_id, link.source_schema, link.source_name),
            (link.peer_connection_id or link.connection_id, link.target_schema, link.target_name),
        ):
            if cid in known and link.status != "rejected":
                items.setdefault(
                    item_key(cid, schema, name),
                    {"connection_id": cid, "schema": schema, "name": name, "kind": "tabular", "row_count": -1},
                )

    relations = []
    for link in flowchart_storage.list_all_links():
        if link.status == "rejected":
            continue
        source = item_key(link.connection_id, link.source_schema, link.source_name)
        target = item_key(link.peer_connection_id or link.connection_id, link.target_schema, link.target_name)
        if source in items and target in items and source != target:
            relations.append((source, target, link))

    with _lock:
        _remove_database_files(path)
    with _connection(path) as conn:
        conn.execute("CREATE NODE TABLE Source(id STRING PRIMARY KEY, name STRING, type STRING)")
        conn.execute(
            "CREATE NODE TABLE Item(key STRING PRIMARY KEY, connection_id STRING, schema_name STRING, "
            "name STRING, kind STRING, row_count INT64)"
        )
        conn.execute("CREATE REL TABLE HAS_ITEM(FROM Source TO Item)")
        conn.execute(
            "CREATE REL TABLE RELATES(FROM Item TO Item, link_id STRING, source_column STRING, target_column STRING, "
            "kind STRING, status STRING, sample_based BOOL, cross_connection BOOL)"
        )
        for saved in connections:
            conn.execute("CREATE (:Source {id: $id, name: $name, type: $type})",
                         {"id": saved.id, "name": saved.name, "type": saved.type})
        for key, item in items.items():
            conn.execute(
                "CREATE (:Item {key: $key, connection_id: $cid, schema_name: $schema, name: $name, "
                "kind: $kind, row_count: $rows})",
                {"key": key, "cid": item["connection_id"], "schema": item["schema"], "name": item["name"],
                 "kind": item["kind"], "rows": item["row_count"]},
            )
            conn.execute(
                "MATCH (s:Source {id: $cid}), (i:Item {key: $key}) CREATE (s)-[:HAS_ITEM]->(i)",
                {"cid": item["connection_id"], "key": key},
            )
        for source, target, link in relations:
            conn.execute(
                "MATCH (a:Item {key: $a}), (b:Item {key: $b}) CREATE (a)-[:RELATES {link_id: $id, "
                "source_column: $sc, target_column: $tc, kind: $kind, status: $status, "
                "sample_based: $sample, cross_connection: $cross}]->(b)",
                {"a": source, "b": target, "id": link.id, "sc": link.source_column, "tc": link.target_column,
                 "kind": link.kind, "status": link.status, "sample": bool(link.sample_based),
                 "cross": link.peer_connection_id is not None},
            )
    stamp = datetime.now(timezone.utc).isoformat()
    _built_at[str(path)] = stamp
    return GraphStatus(True, True, len(connections), len(items), len(relations), stamp)


@timed_phase("graph")
def refresh_quietly() -> None:
    """Keep the derived graph current after a change; never fail the user's action over it."""
    if kuzu is None:
        return
    try:
        rebuild_graph()
    except Exception:
        pass


def graph_status() -> GraphStatus:
    if kuzu is None:
        try:
            _require()
        except GraphUnavailable as exc:
            return GraphStatus(False, False, message=str(exc))
    path = graph_path()
    if not path.exists():
        return GraphStatus(True, False, message="The graph hasn't been built yet.")
    with _connection() as conn:
        sources = _rows(conn, "MATCH (s:Source) RETURN count(s)")[0][0]
        items = _rows(conn, "MATCH (i:Item) RETURN count(i)")[0][0]
        relations = _rows(conn, "MATCH ()-[r:RELATES]->() RETURN count(r)")[0][0]
    return GraphStatus(True, True, sources, items, relations, _built_at.get(str(path)))


def _ensure_built() -> None:
    _require()
    if not graph_path().exists():
        rebuild_graph()


def _item_dict(key, connection_id, schema, name, kind) -> dict:
    return {"key": key, "connection_id": connection_id, "schema": schema, "name": name, "kind": kind}


def neighbors(key: str, hops: int = 2, confirmed_only: bool = False) -> list[dict]:
    """Items reachable from `key` through up to `hops` links (either direction), nearest first."""
    _ensure_built()
    hops = max(1, min(int(hops), MAX_HOPS))
    where = " (r, n | WHERE r.status <> 'guessed')" if confirmed_only else ""
    with _connection() as conn:
        rows = _rows(
            conn,
            f"MATCH (a:Item {{key: $key}})-[e:RELATES* SHORTEST 1..{hops}{where}]-(b:Item) "
            "RETURN b.key, b.connection_id, b.schema_name, b.name, b.kind, length(e) AS distance, "
            "b.connection_id <> a.connection_id AS other_connection ORDER BY distance, b.name",
            {"key": key},
        )
    return [
        {**_item_dict(r[0], r[1], r[2], r[3], r[4]), "distance": r[5], "other_connection": bool(r[6])}
        for r in rows
    ]


def shortest_path(source_key: str, target_key: str, confirmed_only: bool = False) -> dict | None:
    """The shortest chain of links between two items, or None when they aren't connected."""
    _ensure_built()
    where = " (r, n | WHERE r.status <> 'guessed')" if confirmed_only else ""
    with _connection() as conn:
        rows = _rows(
            conn,
            f"MATCH p = (a:Item {{key: $a}})-[e:RELATES* SHORTEST 1..{MAX_HOPS}{where}]-(b:Item {{key: $b}}) "
            "RETURN nodes(p), rels(p)",
            {"a": source_key, "b": target_key},
        )
    if not rows:
        return None
    nodes, rels = rows[0]
    items = [_item_dict(n["key"], n["connection_id"], n["schema_name"], n["name"], n["kind"]) for n in nodes]
    steps = [
        {"source_column": r["source_column"], "target_column": r["target_column"], "kind": r["kind"],
         "status": r["status"], "cross_connection": r["cross_connection"]}
        for r in rels
    ]
    return {"items": items, "links": steps, "length": len(steps)}


_CONFIRMED = "r.status <> 'guessed'"


def neighborhood(key: str, hops: int = 2, confirmed_only: bool = False) -> dict:
    """The picture for one item: it, everything within `hops` links, and the links among them.

    Each node carries its distance from the start and its degree (links in the whole
    graph, counting only confirmed ones when `confirmed_only`), so the screen can size
    the most-connected items up.
    """
    _ensure_built()
    nearby = neighbors(key, hops, confirmed_only)
    keys = [key] + [n["key"] for n in nearby]
    status_filter = f" AND {_CONFIRMED}" if confirmed_only else ""
    with _connection() as conn:
        start = _rows(
            conn,
            "MATCH (i:Item {key: $key}) RETURN i.key, i.connection_id, i.schema_name, i.name, i.kind",
            {"key": key},
        )
        if not start:
            return {"found": False, "nodes": [], "edges": []}
        edge_rows = _rows(
            conn,
            "MATCH (a:Item)-[r:RELATES]->(b:Item) WHERE a.key IN $keys AND b.key IN $keys"
            f"{status_filter} RETURN a.key, b.key, r.link_id, r.source_column, r.target_column, "
            "r.kind, r.status, r.sample_based, r.cross_connection",
            {"keys": keys},
        )
        degree_rows = _rows(
            conn,
            "MATCH (i:Item) WHERE i.key IN $keys OPTIONAL MATCH (i)-[r:RELATES]-() "
            f"{'WHERE ' + _CONFIRMED if confirmed_only else ''} RETURN i.key, count(r)",
            {"keys": keys},
        )
        names = {r[0]: r[1] for r in _rows(conn, "MATCH (s:Source) RETURN s.id, s.name")}
    degrees = dict(degree_rows)
    first = start[0]
    nodes = [{**_item_dict(*first), "distance": 0, "other_connection": False}] + nearby
    for node in nodes:
        node["degree"] = degrees.get(node["key"], 0)
        node["connection_name"] = names.get(node["connection_id"])
    edges = [
        {"source": r[0], "target": r[1], "link_id": r[2], "source_column": r[3], "target_column": r[4],
         "kind": r[5], "status": r[6], "sample_based": bool(r[7]), "cross_connection": bool(r[8])}
        for r in edge_rows
    ]
    return {"found": True, "nodes": nodes, "edges": edges}


def overview(confirmed_only: bool = False) -> dict:
    """Counts, connected groups of items, and the most-connected items.

    With `confirmed_only`, unconfirmed guesses are left out of every figure here -
    the groups, the counts and the degrees - not merely hidden.
    """
    _ensure_built()
    status_filter = f" WHERE {_CONFIRMED}" if confirmed_only else ""
    with _connection() as conn:
        items = {
            r[0]: _item_dict(r[0], r[1], r[2], r[3], r[4])
            for r in _rows(conn, "MATCH (i:Item) RETURN i.key, i.connection_id, i.schema_name, i.name, i.kind")
        }
        edges = _rows(
            conn, f"MATCH (a:Item)-[r:RELATES]->(b:Item){status_filter} RETURN a.key, b.key, r.cross_connection, r.status"
        )
        degrees = dict(
            _rows(
                conn,
                f"MATCH (i:Item) OPTIONAL MATCH (i)-[r:RELATES]-(){status_filter} RETURN i.key, count(r)",
            )
        )
        sources = {r[0]: r[1] for r in _rows(conn, "MATCH (s:Source) RETURN s.id, s.name")}

    # Kuzu has no connected-components routine without a (downloaded) extension,
    # so group the fetched edges here.
    parent = {key: key for key in items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, *_ in edges:
        parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for key in items:
        groups.setdefault(find(key), []).append(key)
    cross_edges = [e for e in edges if e[2]]
    connected = sorted((g for g in groups.values() if len(g) > 1), key=len, reverse=True)
    return {
        "sources": len(sources),
        "items": len(items),
        "relations": len(edges),
        "cross_connection_relations": len(cross_edges),
        "all_items": [
            {**items[k], "connection_name": sources.get(items[k]["connection_id"])}
            for k in sorted(items, key=lambda k: (sources.get(items[k]["connection_id"]) or "", items[k]["name"]))
        ],
        "groups": [
            {"size": len(g), "spans_connections": len({items[k]["connection_id"] for k in g}) > 1,
             "items": [{**items[k], "connection_name": sources.get(items[k]["connection_id"])} for k in sorted(g)]}
            for g in connected
        ],
        "unconnected_items": sum(1 for g in groups.values() if len(g) == 1),
        "most_connected": [
            {**items[k], "connection_name": sources.get(items[k]["connection_id"]), "links": d}
            for k, d in sorted(degrees.items(), key=lambda kv: kv[1], reverse=True)[:5] if d > 0
        ],
    }
