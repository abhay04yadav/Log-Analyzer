"""S5 - Traceback: service dependency graph + source-code location.

* The service graph is rebuilt from spans (span_id / parent_span_id across services) and from an
  optional `peer_service` attribute.  Errors are overlaid on the nodes, so the failure can be followed
  from the visible symptom (usually the edge service) down to the deepest failing dependency.
* Stack frames are mapped to the repository snapshot: the innermost application frame is located in
  the source tree, and the enclosing function and a code snippet are extracted (Python via `ast`,
  Java / JS via lightweight signature heuristics).
"""
import ast
import os
import re
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.models import LogEvent
from app.pipeline.fingerprint import is_app_frame

settings = get_settings()


# ---------------------------------------------------------------- service graph
def build_graph(events: list[LogEvent]) -> dict:
    spans = {e.span_id: e.service for e in events if e.span_id}
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str], dict] = {}
    for e in events:
        n = nodes.setdefault(e.service, {"id": e.service, "events": 0, "errors": 0, "first_error": None})
        n["events"] += 1
        if e.is_error:
            n["errors"] += 1
            if n["first_error"] is None or e.ts < n["first_error"]:
                n["first_error"] = e.ts
        parent = spans.get(e.parent_span_id) if e.parent_span_id else None
        peer = (e.attrs or {}).get("peer_service")
        for src, dst in ((parent, e.service), (e.service, peer)):
            if src and dst and src != dst:
                ed = edges.setdefault((src, dst), {"source": src, "target": dst, "calls": 0, "errors": 0})
                ed["calls"] += 1
                ed["errors"] += int(e.is_error)
    # failing node with no failing downstream = where the error propagation starts
    for name, n in nodes.items():
        down = [d for (s, d) in edges if s == name]
        n["downstream"] = down
        n["upstream"] = [s for (s, d) in edges if d == name]
        n["origin"] = n["errors"] > 0 and not any(nodes.get(d, {}).get("errors") for d in down)
        n["depth"] = 0
    # depth from roots (no upstream) for layout
    roots = [k for k, n in nodes.items() if not n["upstream"]] or list(nodes)
    seen, frontier, depth = set(roots), list(roots), 0
    while frontier:
        nxt = []
        for k in frontier:
            nodes[k]["depth"] = depth
            for d in nodes[k]["downstream"]:
                if d not in seen and d in nodes:
                    seen.add(d)
                    nxt.append(d)
        frontier, depth = nxt, depth + 1
    for n in nodes.values():
        if n["first_error"] is not None:
            n["first_error"] = n["first_error"].isoformat() + "Z"
    return {"nodes": sorted(nodes.values(), key=lambda n: (n["depth"], n["id"])), "edges": list(edges.values())}


def reachable_upstream(graph: dict, service: str) -> set[str]:
    """Services that (transitively) call `service` - i.e. those impacted when it fails."""
    up = {n["id"]: n["upstream"] for n in graph["nodes"]}
    out, stack = set(), [service]
    while stack:
        for u in up.get(stack.pop(), []):
            if u not in out:
                out.add(u)
                stack.append(u)
    return out


# ---------------------------------------------------------------- code location
@lru_cache(maxsize=1)
def _repo_files() -> list[str]:
    root = Path(settings.code_repo_path)
    if not root.exists():
        return []
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
        files += [Path(dirpath, f).relative_to(root).as_posix() for f in filenames]
    return files


def _frame_path(frame: dict) -> str:
    if frame.get("lang") == "java" and frame.get("module"):
        pkg = frame["module"].rsplit(".", 1)[0].replace(".", "/")
        return f"{pkg}/{frame['file']}"
    return frame.get("file", "").replace("\\", "/")


def resolve_file(service: str, frame: dict) -> str | None:
    want = _frame_path(frame).lstrip("./").split("/")
    best, best_len = None, 0
    for rel in _repo_files():
        parts = rel.split("/")
        n = 0
        while n < min(len(parts), len(want)) and parts[-1 - n] == want[-1 - n]:
            n += 1
        if n == 0:
            continue
        n += 0.5 if parts[0] == service else 0      # prefer the service's own folder
        if n > best_len:
            best, best_len = rel, n
    return best


def _python_function(source: str, line: int) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if best is None or node.lineno >= best.lineno:
                    best = node
    if best is None:
        return None
    if isinstance(best, ast.ClassDef):
        return best.name
    owner = next((c.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef)
                  and c.lineno <= best.lineno <= (c.end_lineno or c.lineno)), None)
    return f"{owner}.{best.name}" if owner else best.name


SIG = re.compile(r"^\s*(?:public|private|protected|static|final|async|function|\s)*[\w<>\[\],\s]*?\b(\w+)\s*\([^;]*$")


def _signature_function(lines: list[str], line: int) -> str | None:
    for i in range(min(line, len(lines)) - 1, -1, -1):
        m = SIG.match(lines[i])
        if m and m.group(1) not in ("if", "for", "while", "switch", "catch", "return", "new"):
            return m.group(1)
    return None


def code_location(service: str, frames: list[dict] | None) -> dict | None:
    app = [f for f in (frames or []) if is_app_frame(f)]
    if not app:
        return None
    frame = app[0]                                   # innermost application frame
    rel = resolve_file(service, frame)
    loc = {"file": _frame_path(frame), "line": frame.get("line"), "function": frame.get("function"),
           "language": frame.get("lang"), "resolved": False}
    if not rel:
        return loc
    path = Path(settings.code_repo_path, rel)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return loc
    lines = source.splitlines()
    line = frame.get("line") or 1
    start, end = max(1, line - 6), min(len(lines), line + 4)
    func = _python_function(source, line) if rel.endswith(".py") else _signature_function(lines, line)
    loc.update(resolved=True, repo_path=rel, function=func or frame.get("function"),
               start_line=start, snippet=lines[start - 1:end])
    return loc
