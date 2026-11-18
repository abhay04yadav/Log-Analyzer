"""S2 - Normalise heterogeneous log input into one canonical event schema.

Accepted inputs (per item):
  * a JSON object (dict) or a JSON string
  * a logfmt line            ts=... level=error service=payment msg="..."
  * a plain-text line        2026-11-18 10:00:01,123 ERROR [checkout-service] message
    optionally followed by a multi-line Python / Java / Node stack trace
Secrets are masked before anything is stored or sent to an AI provider.
"""
import json
import re
import shlex
from datetime import UTC, datetime

from dateutil import parser as dtparser

from app.db import utcnow

LEVELS = {"trace": "DEBUG", "debug": "DEBUG", "info": "INFO", "information": "INFO", "notice": "INFO",
          "warn": "WARN", "warning": "WARN", "error": "ERROR", "err": "ERROR", "severe": "ERROR",
          "critical": "CRITICAL", "crit": "CRITICAL", "fatal": "CRITICAL", "alert": "CRITICAL", "emerg": "CRITICAL"}

KEYS = {
    "ts": ("timestamp", "@timestamp", "time", "ts", "datetime", "date"),
    "level": ("level", "severity", "lvl", "log.level", "loglevel"),
    "message": ("message", "msg", "log", "text"),
    "service": ("service", "service.name", "service_name", "app", "application", "component"),
    "logger": ("logger", "logger_name", "log.logger", "name"),
    "host": ("host", "hostname", "host.name", "pod"),
    "trace_id": ("trace_id", "traceId", "trace.id", "traceid", "trace"),
    "span_id": ("span_id", "spanId", "span.id", "span"),
    "parent_span_id": ("parent_span_id", "parentSpanId", "parent_id", "parent.span.id"),
    "request_id": ("request_id", "requestId", "req_id", "x_request_id"),
    "stack": ("stack_trace", "stacktrace", "stack", "exception", "exc_info", "error.stack", "traceback"),
    "error_type": ("error_type", "exception_type", "error.type", "exc_type"),
}

# ---------------------------------------------------------------- secret masking
MASKS = [
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|authorization)"
                r"(\s*[=:]\s*|\"\s*:\s*\")([^\s\",;&]+)"), lambda m: f"{m.group(1)}{m.group(2)}***"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*"), lambda m: "Bearer ***"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), lambda m: "<jwt>"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), lambda m: "<card>"),
    (re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"),
     lambda m: f"{m.group(1)}***@{m.group(2)}"),
    (re.compile(r"(?i)(://[^:/\s]+:)([^@\s]+)(@)"), lambda m: f"{m.group(1)}***{m.group(3)}"),  # db URLs
]


def mask(text: str | None) -> str | None:
    if not text:
        return text
    for rx, rep in MASKS:
        text = rx.sub(rep, text)
    return text


def mask_obj(obj):
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: ("***" if re.search(r"(?i)password|secret|token|api_?key|authorization", k) else mask_obj(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_obj(v) for v in obj]
    return obj


# ---------------------------------------------------------------- stack traces
PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)')
PY_EXC = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Timeout\w*)|"
                    r"[a-z_][\w]*\.[\w.]*[A-Z]\w*)(?::\s?(?P<msg>.*))?$")
JAVA_FRAME = re.compile(r"^\s*at (?P<cls>[\w$.]+)\.(?P<func>[\w$<>]+)\((?P<file>[^:()]+)(?::(?P<line>\d+))?\)")
JAVA_EXC = re.compile(r"^(?:Caused by: )?(?P<type>(?:[a-z_][\w]*\.)+[A-Z][\w$]*(?:Exception|Error|Throwable)"
                      r"|[A-Z]\w*(?:Exception|Error))(?::\s?(?P<msg>.*))?$")
NODE_FRAME = re.compile(r"^\s*at (?:(?P<func>[^\s(]+) \()?(?P<file>[^():]+):(?P<line>\d+):\d+\)?")


def parse_stack(text: str) -> tuple[list[dict], str | None, str | None]:
    """Return (frames innermost-first, error_type, error_message)."""
    if not text:
        return [], None, None
    lines = text.strip("\n").splitlines()
    py, java, node = [], [], []
    etype = emsg = None
    for ln in lines:
        if m := PY_FRAME.match(ln):
            py.append(dict(file=m["file"], line=int(m["line"]), function=m["func"], lang="python"))
        elif m := JAVA_FRAME.match(ln):
            java.append(dict(file=m["file"], line=int(m["line"] or 0), function=m["func"], module=m["cls"],
                             lang="java"))
        elif m := NODE_FRAME.match(ln):
            node.append(dict(file=m["file"], line=int(m["line"]), function=m["func"] or "<anonymous>", lang="node"))
    if py:
        # Python: exception line is the last non-frame line; frames are outermost-first
        for ln in reversed(lines):
            s = ln.strip()
            if s and not s.startswith(("File ", "Traceback", "^", "~")) and (m := PY_EXC.match(s)):
                etype, emsg = m["type"], m["msg"]
                break
        return list(reversed(py)), etype, emsg
    if java:
        # Java: use the deepest "Caused by" when present, else the first exception line
        causes = [ln.strip() for ln in lines if ln.strip().startswith("Caused by:")]
        head = causes[-1] if causes else next((ln.strip() for ln in lines if JAVA_EXC.match(ln.strip())), None)
        if head and (m := JAVA_EXC.match(head)):
            etype, emsg = m["type"], m["msg"]
        return java, etype, emsg
    if node:
        first = lines[0].strip()
        if ":" in first:
            etype, emsg = first.split(":", 1)[0].strip(), first.split(":", 1)[1].strip()
        return node, etype, emsg
    return [], None, None


# ---------------------------------------------------------------- formats
LOGFMT_HINT = re.compile(r"^\s*\w[\w.]*=")
TEXT_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"(?:\[(?P<lvl1>[A-Za-z]+)\]|(?P<lvl2>[A-Za-z]+))\s+"
    r"(?:\[(?P<svc>[^\]]+)\]\s+)?(?:(?P<logger>[\w.$]+)\s+-\s+)?(?P<msg>.*)$")


def _parse_ts(value) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            v = float(value)
            v = v / 1000 if v > 1e12 else v
            return datetime.fromtimestamp(v, UTC).replace(tzinfo=None)
        dt = dtparser.parse(str(value).replace(",", "."))
        if dt.tzinfo:
            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except (ValueError, OverflowError, TypeError):
        return None


def _flatten(d: dict, prefix="") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and k not in ("attrs", "attributes"):
            out.update(_flatten(v, key + "."))
        out[key] = v
    return out


def _pick(flat: dict, field: str):
    for k in KEYS[field]:
        if k in flat and flat[k] not in (None, "") and not isinstance(flat[k], dict):
            return flat.pop(k)
    return None


def _from_mapping(obj: dict, fmt: str) -> dict:
    flat = _flatten(obj)
    ev = {f: _pick(flat, f) for f in KEYS}
    stack = ev["stack"]
    if isinstance(stack, list):
        stack = "\n".join(map(str, stack))
    ev["stack"] = stack
    known = {k for f in KEYS.values() for k in f}
    attrs = obj.get("attrs") or obj.get("attributes") or {}
    attrs = dict(attrs) if isinstance(attrs, dict) else {}
    for k, v in obj.items():
        if k not in known and k not in ("attrs", "attributes") and not isinstance(v, (dict, list)):
            attrs[k] = v
    ev["attrs"] = attrs
    ev["format"] = fmt
    return ev


def _parse_logfmt(line: str) -> dict | None:
    try:
        parts = shlex.split(line, posix=True)
    except ValueError:
        return None
    obj = {}
    for p in parts:
        if "=" not in p:
            return None
        k, v = p.split("=", 1)
        obj[k] = v
    return _from_mapping(obj, "logfmt") if obj else None


def _parse_text(text: str) -> dict:
    first, _, rest = text.partition("\n")
    m = TEXT_LINE.match(first.strip())
    if m:
        ev = dict(ts=m["ts"], level=m["lvl1"] or m["lvl2"], service=m["svc"], logger=m["logger"],
                  message=m["msg"], stack=rest or None, attrs={}, format="text")
    else:
        ev = dict(ts=None, level=None, service=None, logger=None, message=first, stack=rest or None,
                  attrs={}, format="text")
        lv = re.search(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b", first)
        ev["level"] = lv.group(1) if lv else None
    for k in ("trace_id", "span_id", "parent_span_id", "request_id", "host", "error_type"):
        ev.setdefault(k, None)
    # inline key=value context inside free text, e.g. "trace_id=abc span_id=def"
    for k in ("trace_id", "span_id", "parent_span_id", "request_id"):
        if mm := re.search(rf"\b{k}=([\w-]+)", text):
            ev[k] = mm.group(1)
    return ev


def normalise(item, default_service: str | None = None, max_chars: int = 16000) -> dict:
    """Turn one raw input item into the canonical event dict (not yet persisted)."""
    raw_text = item if isinstance(item, str) else json.dumps(item, default=str)
    if isinstance(item, dict):
        ev = _from_mapping(item, "json")
    else:
        s = str(item).strip()
        ev = None
        if s.startswith("{"):
            try:
                ev = _from_mapping(json.loads(s), "json")
            except json.JSONDecodeError:
                ev = None
        if ev is None and LOGFMT_HINT.match(s) and "\n" not in s:
            ev = _parse_logfmt(s)
        if ev is None:
            ev = _parse_text(s)

    message = str(ev.get("message") or "").strip()
    stack_text = ev.get("stack")
    if not stack_text and "\n" in message:            # stack trace embedded in the message
        message, _, stack_text = message.partition("\n")
    frames, etype, emsg = parse_stack(stack_text or "")
    if not frames and (m := PY_EXC.match(message) or JAVA_EXC.match(message)):
        etype = etype or m["type"]
    level = LEVELS.get(str(ev.get("level") or "").lower(), None)
    if level is None:
        level = "ERROR" if frames or etype else "INFO"
    error_type = ev.get("error_type") or etype
    is_error = level in ("ERROR", "CRITICAL") or bool(frames)
    if not message and emsg:
        message = emsg
    elif ev.get("format") == "text" and etype and etype not in message:
        message = f"{message}: {etype}" + (f": {emsg}" if emsg else "")   # free text: surface the exception
    message = re.sub(r"\s*\b(trace_id|span_id|parent_span_id|request_id)=[\w-]+", "", message).strip()

    ts = _parse_ts(ev.get("ts")) or utcnow()
    attrs = mask_obj(ev.get("attrs") or {})
    return dict(
        ts=ts,
        service=str(ev.get("service") or default_service or "unknown")[:120],
        level=level,
        message=mask(message)[:max_chars],
        logger=(str(ev["logger"])[:200] if ev.get("logger") else None),
        host=(str(ev["host"])[:120] if ev.get("host") else None),
        trace_id=(str(ev["trace_id"])[:64] if ev.get("trace_id") else None),
        span_id=(str(ev["span_id"])[:64] if ev.get("span_id") else None),
        parent_span_id=(str(ev["parent_span_id"])[:64] if ev.get("parent_span_id") else None),
        request_id=(str(ev["request_id"])[:64] if ev.get("request_id") else None),
        is_error=is_error,
        error_type=(str(error_type)[:200] if error_type else None),
        stack=frames or None,
        stack_text=mask(stack_text)[:max_chars] if stack_text else None,
        attrs=attrs,
        source_format=ev.get("format", "text"),
        raw=mask(raw_text)[:max_chars],
    )
