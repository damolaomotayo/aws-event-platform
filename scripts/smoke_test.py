#!/usr/bin/env python3
"""End-to-end check against the deployed stack. Standard library only.

    python3 scripts/smoke_test.py            # core checks (~10 seconds)
    python3 scripts/smoke_test.py --with-dlq # also prove failed events reach the DLQ (~2 minutes)
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
passed = 0


def check(name, condition, detail=""):
    global passed
    if not condition:
        print(f"FAIL  {name} {detail}")
        sys.exit(1)
    passed += 1
    print(f"ok    {name}")


def tf_outputs():
    out = subprocess.run(
        ["terraform", f"-chdir={ROOT / 'terraform'}", "output", "-json"],
        check=True, capture_output=True, text=True,
    ).stdout
    return {k: v["value"] for k, v in json.loads(out).items()}


def call(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def wait_for_event(api, event_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, body = call("GET", f"{api}/events/{event_id}")
        if status == 200:
            return body
        time.sleep(1)
    return None


def dlq_depth(out):
    raw = subprocess.run(
        ["aws", "sqs", "get-queue-attributes", "--queue-url", out["dlq_url"],
         "--attribute-names", "ApproximateNumberOfMessages", "--region", out["region"], "--output", "json"],
        check=True, capture_output=True, text=True,
    ).stdout
    return int(json.loads(raw)["Attributes"]["ApproximateNumberOfMessages"])


def main():
    out = tf_outputs()
    api = out["api_url"].rstrip("/")
    print(f"API: {api}\n")

    # 1. Happy path: accepted, flows through EventBridge -> SQS -> Lambda -> DynamoDB.
    status, body = call("POST", f"{api}/events", {"type": "order.created", "payload": {"order_id": 42, "total": 19.99}})
    check("POST /events returns 202", status == 202, str(body))
    event_id = body["event_id"]
    stored = wait_for_event(api, event_id)
    check("event appears in DynamoDB via the pipeline", stored is not None)
    check("payload round-trips intact", stored["payload"] == {"order_id": 42, "total": 19.99})

    # 2. Validation.
    status, _ = call("POST", f"{api}/events", {"type": "NotValid"})
    check("invalid type is rejected with 400", status == 400)

    # 3. Idempotency: the same key sent twice must produce exactly one record.
    key = f"smoke-{uuid.uuid4().hex[:12]}"
    for _ in range(2):
        status, body = call("POST", f"{api}/events", {"type": "smoke.duplicate"}, {"Idempotency-Key": key})
        check("duplicate POST accepted", status == 202)
    time.sleep(5)
    status, listing = call("GET", f"{api}/events?type=smoke.duplicate&limit=100")
    matches = [e for e in listing["events"] if e["event_id"] == key]
    check("idempotency key stored exactly once", len(matches) == 1, f"found {len(matches)}")

    # 4. Listing by type.
    status, listing = call("GET", f"{api}/events?type=order.created")
    check("list by type returns the event", any(e["event_id"] == event_id for e in listing["events"]))

    # 5. Not found.
    status, _ = call("GET", f"{api}/events/does-not-exist")
    check("unknown id returns 404", status == 404)

    # 6. Optional: failing events end up in the dead-letter queue.
    if "--with-dlq" in sys.argv:
        before = dlq_depth(out)
        call("POST", f"{api}/events", {"type": "order.failed", "payload": {"simulate_failure": True}})
        print("      waiting for 3 failed attempts (about 90s)...")
        deadline = time.time() + 180
        while time.time() < deadline and dlq_depth(out) <= before:
            time.sleep(10)
        check("failing event lands in the DLQ", dlq_depth(out) > before)

    print(f"\nAll {passed} checks passed.")


if __name__ == "__main__":
    main()
