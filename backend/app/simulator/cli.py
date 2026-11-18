"""Standalone simulator: plays a scenario against the HTTP ingestion API (like a real log shipper).

usage:  python -m app.simulator.cli db_pool_exhaustion [--url http://localhost:8000] [--key sla_demo_ingest_key]
"""
import argparse
import time

import httpx

from app.db import utcnow
from app.simulator import scenarios


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(scenarios.GENERATORS))
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--key", default="sla_demo_ingest_key")
    args = ap.parse_args()

    headers = {"X-API-Key": args.key}
    steps = scenarios.build(args.scenario, utcnow())
    t0, i, sent = time.monotonic(), 0, 0
    with httpx.Client(base_url=args.url, headers=headers, timeout=10) as client:
        while i < len(steps):
            now = time.monotonic() - t0
            batch = []
            while i < len(steps) and steps[i][0] <= now + 0.25:
                _, kind, item = steps[i]
                if kind == "deploy":
                    client.post("/api/v1/deployments", json=item).raise_for_status()
                    print(f"deployment: {item['service']} {item['version']}")
                else:
                    batch.append(item)
                i += 1
            if batch:
                client.post("/api/v1/ingest", json={"events": batch}).raise_for_status()
                sent += len(batch)
                print(f"\rsent {sent} events", end="", flush=True)
            time.sleep(0.5)
    print(f"\ndone: {args.scenario}")


if __name__ == "__main__":
    main()
