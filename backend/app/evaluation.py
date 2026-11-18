"""Evaluation harness (synopsis section 8.3): measures the pipeline against ground truth.

Each run replays all four simulator scenarios *overlapping in time* (random start offsets and random
request timing), mixed with healthy background traffic and harmless noise errors, through the real
pipeline (normalise -> fingerprint -> detect -> correlate -> traceback -> rank -> recommend) on an
isolated temporary database.  Because the simulator knows which scenario produced every log line,
the results can be scored exactly.

Metrics
  * incident detection rate           scenarios that produced an incident
  * false-positive / split incidents  incidents that do not correspond to exactly one scenario
  * grouping precision / recall / F1  pairwise, over failure events (errors + failed logins)
  * time to detect (simulated)        first failure event -> incident opened
  * root cause top-1 / top-3          expected service + error type among the ranked candidates
  * single-signal ablation            top-1 accuracy when ranking by T, D, A, C or H alone
  * recommendation validity           validator pass rate and recommendation source

usage:  python -m app.evaluation [--runs 10] [--seed 1] [--llm] [--out ../docs/evaluation.md]
"""
import argparse
import json
import os
import random
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from math import comb
from pathlib import Path

# isolated database, in-process processing, no background worker (set before the app is imported)
_TMP = Path(tempfile.mkdtemp(prefix="sla-eval-"))
os.environ.update(DATABASE_URL=f"sqlite:///{(_TMP / 'eval.db').as_posix()}", REDIS_URL="", RUN_WORKER="false")
if "--llm" not in sys.argv:
    os.environ["GEMINI_API_KEY"] = ""

from sqlalchemy import select  # noqa: E402

from app.api.ingest import store_deployment  # noqa: E402
from app.db import Base, SessionLocal, engine, init_db, utcnow  # noqa: E402
from app.models import Incident, LogEvent  # noqa: E402
from app.pipeline.detect import is_auth_failure  # noqa: E402
from app.pipeline.processor import process_batch  # noqa: E402
from app.pipeline.recommend import recommend  # noqa: E402
from app.seed import seed  # noqa: E402
from app.simulator import scenarios  # noqa: E402

EXPECTED = {   # scenario -> (category, root-cause service, error-type fragment)
    "db_pool_exhaustion": ("error", "payment-service", "TimeoutError"),
    "inventory_null_pointer": ("error", "inventory-service", "NullPointerException"),
    "cache_outage": ("error", "cart-service", "ConnectionError"),
    "brute_force_login": ("security", "auth-service", "authentication"),
}
SIGNALS = ["T", "D", "A", "C", "H"]


def _skew(item, seconds: float):
    """Shift the timestamp of a plain-text gateway line (simulates clock skew between hosts)."""
    ts, rest = item.split(" ", 1)
    t = datetime.fromisoformat(ts.replace("Z", "")) - timedelta(seconds=seconds)
    return t.isoformat(timespec="milliseconds") + "Z " + rest


def build_run(seed_: int):
    """All scenarios overlapping in time + confounders + noise; returns time-ordered (t, kind, item, label).

    Confounders (so that no single signal is enough):
      * clock skew: in every second run the api-gateway host clock is 0.3-0.9 s fast, so the gateway's
        (symptom) errors appear *before* the real root cause - misleads the temporal signal T
      * red-herring deployment: api-gateway is redeployed shortly before every run - misleads C
      * noise: isolated, harmless errors that must not open incidents
    """
    random.seed(seed_)
    base = utcnow() - timedelta(minutes=20)
    skew = random.uniform(0.3, 0.9) if seed_ % 2 == 0 else 0.0
    steps = [(0.0, "deploy", dict(service="api-gateway", version="v5.2.0", commit="77aa001", author="platform",
                                  ts=(base - timedelta(minutes=3)).isoformat() + "Z",
                                  description="Routine gateway config update", changed_files=["nginx.conf"]),
              "noise")]
    names = list(EXPECTED)
    random.shuffle(names)
    t0 = 0.0
    for name in names:
        start = base + timedelta(seconds=t0)
        for off, kind, item in scenarios.build(name, start):
            if skew and kind == "log" and isinstance(item, str) and "[api-gateway]" in item and " ERROR " in item:
                item = _skew(item, skew)
            steps.append((t0 + off, kind, item, name))
        t0 += random.uniform(3, 15)                      # scenarios overlap
    for t in (random.uniform(0, 20), random.uniform(45, 70)):   # isolated noise errors (< 1 per minute)
        steps.append((t, "log", scenarios.logfmt(base + timedelta(seconds=t), "error", "checkout-service",
                                                 "CouponValidationError: coupon code expired",
                                                 error_type="CouponValidationError"), "noise"))
    steps.sort(key=lambda s: s[0])
    return base, steps


def pairwise_f1(true: list, pred: list) -> tuple[float, float, float]:
    pairs = lambda labels: sum(comb(n, 2) for n in Counter(labels).values())  # noqa: E731
    tp = pairs(list(zip(true, pred)))
    p_pairs, t_pairs = pairs(pred), pairs(true)
    precision = tp / p_pairs if p_pairs else 1.0
    recall = tp / t_pairs if t_pairs else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def matches(cand, expected) -> bool:
    _, service, fragment = expected
    return cand.service == service and fragment.lower() in (cand.error_type or cand.message or "").lower()


def run_once(seed_: int, use_llm: bool) -> dict:
    Base.metadata.drop_all(engine)
    init_db()
    seed()
    base, steps = build_run(seed_)
    labels: list[str] = []
    detected_at: dict[int, float] = {}
    with SessionLocal() as db:
        batch, batch_labels, t_end = [], [], 1.0
        for i, (t, kind, item, label) in enumerate(steps):
            if kind == "deploy":
                store_deployment(db, 1, item)
                db.commit()
                continue
            batch.append(item)
            batch_labels.append(label)
            last = i == len(steps) - 1 or steps[i + 1][0] > t_end
            if last:
                process_batch(db, 1, batch)
                labels += batch_labels
                for inc_id in db.scalars(select(Incident.id)):
                    detected_at.setdefault(inc_id, t)
                batch, batch_labels = [], []
                t_end = (steps[i + 1][0] if i + 1 < len(steps) else t) + 1.0

        events = list(db.scalars(select(LogEvent).order_by(LogEvent.id)))
        assert len(events) == len(labels), "event/label alignment broken"
        failure = [(e, lab) for e, lab in zip(events, labels) if e.is_error or is_auth_failure(e)]
        true = [lab if lab != "noise" else f"noise-{e.id}" for e, lab in failure]
        pred = [f"inc-{e.incident_id}" if e.incident_id else f"none-{e.id}" for e, _ in failure]
        precision, recall, f1 = pairwise_f1(true, pred)

        first_fail = {}
        for e, lab in failure:
            first_fail.setdefault(lab, (e.ts - base).total_seconds())

        incidents = list(db.scalars(select(Incident).order_by(Incident.id)))
        by_scenario: dict[str, list[Incident]] = defaultdict(list)
        false_pos = 0
        for inc in incidents:
            labs = Counter(lab for e, lab in failure if e.incident_id == inc.id)
            top = labs.most_common(1)[0][0] if labs else "none"
            if top in EXPECTED:
                by_scenario[top].append(inc)
            else:
                false_pos += 1
        splits = sum(len(v) - 1 for v in by_scenario.values())

        per = {}
        ablation = {k: 0 for k in SIGNALS}
        for name, exp in EXPECTED.items():
            incs = by_scenario.get(name, [])
            if not incs:
                per[name] = {"detected": False}
                continue
            inc = max(incs, key=lambda x: x.event_count)
            cands = inc.candidates
            rank = next((c.rank for c in cands if matches(c, exp)), None)
            for k in SIGNALS:                       # rank by a single signal; ties count as a miss
                best = max((c.signals[k] for c in cands), default=0)
                top = [c for c in cands if c.signals[k] == best]
                ablation[k] += int(len(top) == 1 and matches(top[0], exp))
            rec = recommend(db, inc)
            db.commit()
            per[name] = {"detected": True, "category_ok": inc.category == exp[0], "rank": rank,
                         "confidence": cands[0].confidence if cands else None,
                         "ttd": detected_at[inc.id] - first_fail.get(name, detected_at[inc.id]),
                         "rec_source": rec.source if rec else None,
                         "rec_valid": bool(rec and rec.validation["status"] == "passed")}
    return {"seed": seed_, "precision": precision, "recall": recall, "f1": f1, "incidents": len(incidents),
            "false_positives": false_pos, "splits": splits, "per": per, "ablation": ablation,
            "events": len(labels)}


def summarise(results: list[dict]) -> tuple[str, dict]:
    n_runs = len(results)
    cases = [(r["seed"], name, p) for r in results for name, p in r["per"].items()]
    det = [p for _, _, p in cases if p["detected"]]
    top1 = sum(1 for p in det if p["rank"] == 1)
    top3 = sum(1 for p in det if p["rank"] and p["rank"] <= 3)
    ttd = [p["ttd"] for p in det]
    valid = sum(1 for p in det if p["rec_valid"])
    n = len(cases)
    abl = {k: sum(r["ablation"][k] for r in results) / n for k in SIGNALS}
    sources = Counter(p["rec_source"] for p in det)
    summary = {
        "runs": n_runs, "scenario_cases": n, "events": sum(r["events"] for r in results),
        "detection_rate": len(det) / n, "top1": top1 / n, "top3": top3 / n,
        "grouping_precision": statistics.mean(r["precision"] for r in results),
        "grouping_recall": statistics.mean(r["recall"] for r in results),
        "grouping_f1": statistics.mean(r["f1"] for r in results),
        "false_positive_incidents": sum(r["false_positives"] for r in results),
        "split_incidents": sum(r["splits"] for r in results),
        "ttd_mean_s": statistics.mean(ttd) if ttd else None, "ttd_max_s": max(ttd) if ttd else None,
        "recommendation_valid": valid / len(det) if det else 0, "recommendation_sources": dict(sources),
        "ablation_top1": abl,
        "mean_top_confidence": statistics.mean(p["confidence"] for p in det if p["confidence"] is not None),
    }
    per_scenario = []
    for name in EXPECTED:
        ps = [p for _, nm, p in cases if nm == name]
        d = [p for p in ps if p["detected"]]
        per_scenario.append((name, len(d), len(ps), sum(1 for p in d if p["rank"] == 1),
                             statistics.mean(p["ttd"] for p in d) if d else float("nan"),
                             statistics.mean(p["confidence"] for p in d) if d else float("nan")))

    pct = lambda x: f"{100 * x:.1f}%"  # noqa: E731
    md = [
        "# Evaluation results",
        "",
        f"Generated by `python -m app.evaluation` - {n_runs} runs x 4 overlapping scenarios "
        f"({summary['events']:,} log events), synthetic ShopFlow workload with background traffic and noise errors.",
        "",
        "| Metric | Result |", "|---|---|",
        f"| Incident detection rate | {pct(summary['detection_rate'])} |",
        f"| Root cause top-1 accuracy | {pct(summary['top1'])} |",
        f"| Root cause top-3 accuracy | {pct(summary['top3'])} |",
        f"| Grouping precision / recall / F1 (pairwise) | {summary['grouping_precision']:.3f} / "
        f"{summary['grouping_recall']:.3f} / {summary['grouping_f1']:.3f} |",
        f"| False-positive incidents (noise) | {summary['false_positive_incidents']} |",
        f"| Split incidents (one failure, several incidents) | {summary['split_incidents']} |",
        f"| Time to detect, mean / max (simulated) | {summary['ttd_mean_s']:.1f} s / {summary['ttd_max_s']:.1f} s |",
        f"| Recommendations passing the validator | {pct(summary['recommendation_valid'])} |",
        f"| Recommendation sources | {', '.join(f'{k}: {v}' for k, v in sources.items())} |",
        f"| Mean confidence of the top candidate | {summary['mean_top_confidence']:.2f} |",
        "",
        "## Per scenario", "",
        "| Scenario | Detected | Top-1 correct | Mean time to detect | Mean confidence |", "|---|---|---|---|---|",
        *[f"| {nm} | {d}/{t} | {c}/{t} | {ttd:.1f} s | {cf:.2f} |" for nm, d, t, c, ttd, cf in per_scenario],
        "",
        "## Ablation: ranking with a single signal", "",
        "Top-1 accuracy when candidates are ranked by one signal only (ties count as a miss), compared with the "
        "combined score R.", "",
        "| Ranking by | Top-1 accuracy |", "|---|---|",
        *[f"| {k} only | {pct(abl[k])} |" for k in SIGNALS],
        f"| **R (combined)** | **{pct(summary['top1'])}** |",
        "",
        "## Notes", "",
        "* Data is synthetic: the simulator's failure scenarios are the ground truth. Accuracy on real "
        "production logs will be lower and must be measured on labelled incidents.",
        "* Time to detect is measured on the logs' own timestamps, i.e. how many seconds of failure data were "
        "needed before an incident was opened (excluding the AI step).",
    ]
    return "\n".join(md) + "\n", summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--llm", action="store_true", help="use the configured AI provider for recommendations")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "docs" / "evaluation.md"))
    args = ap.parse_args()
    t = time.time()
    results = []
    for i in range(args.runs):
        r = run_once(args.seed + i, args.llm)
        results.append(r)
        print(f"run {i + 1}/{args.runs}: incidents={r['incidents']} F1={r['f1']:.3f} "
              f"ranks={ {k[:10]: v.get('rank') for k, v in r['per'].items()} }")
    md, summary = summarise(results)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({"summary": summary, "runs": results}, indent=2, default=str),
                                        encoding="utf-8")
    print("\n" + md)
    print(f"written to {out} ({time.time() - t:.0f} s)")


if __name__ == "__main__":
    main()
