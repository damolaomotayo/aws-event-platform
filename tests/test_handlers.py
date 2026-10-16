import json

from conftest import load


def api_event(body, headers=None):
    return {"body": json.dumps(body) if not isinstance(body, str) else body, "headers": headers or {}}


def sqs_record(message_id, event_id, event_type="order.created", payload=None):
    detail = {
        "event_id": event_id,
        "type": event_type,
        "payload": payload or {},
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    return {"messageId": message_id, "body": json.dumps({"detail": detail})}


# --- ingest ---------------------------------------------------------------

def test_ingest_accepts_valid_event(aws):
    ingest = load("ingest")
    resp = ingest.handler(api_event({"type": "order.created", "payload": {"id": 1}}), None)
    assert resp["statusCode"] == 202
    assert json.loads(resp["body"])["status"] == "accepted"


def test_ingest_uses_idempotency_key_as_event_id(aws):
    ingest = load("ingest")
    resp = ingest.handler(
        api_event({"type": "order.created"}, headers={"Idempotency-Key": "abc12345-key"}), None
    )
    assert json.loads(resp["body"])["event_id"] == "abc12345-key"


def test_ingest_rejects_bad_input(aws):
    ingest = load("ingest")
    assert ingest.handler(api_event("not json"), None)["statusCode"] == 400
    assert ingest.handler(api_event([1, 2]), None)["statusCode"] == 400
    assert ingest.handler(api_event({"type": "BadType"}), None)["statusCode"] == 400
    assert ingest.handler(api_event({"type": "a.b", "payload": "x"}), None)["statusCode"] == 400
    bad_key = api_event({"type": "a.b"}, headers={"idempotency-key": "short"})
    assert ingest.handler(bad_key, None)["statusCode"] == 400


# --- processor ------------------------------------------------------------

def test_processor_stores_event(aws):
    processor = load("processor")
    out = processor.handler({"Records": [sqs_record("m1", "evt-1", payload={"n": 5})]}, None)
    assert out == {"batchItemFailures": []}
    item = aws.get_item(Key={"event_id": "evt-1"})["Item"]
    assert json.loads(item["payload_json"]) == {"n": 5}


def test_processor_is_idempotent(aws):
    processor = load("processor")
    record = sqs_record("m1", "evt-dup")
    processor.handler({"Records": [record]}, None)
    out = processor.handler({"Records": [record]}, None)
    assert out == {"batchItemFailures": []}
    assert aws.scan()["Count"] == 1


def test_processor_reports_only_failed_messages(aws):
    processor = load("processor")
    good = sqs_record("good", "evt-good")
    bad = sqs_record("bad", "evt-bad", payload={"simulate_failure": True})
    broken = {"messageId": "broken", "body": "{not json"}
    out = processor.handler({"Records": [good, bad, broken]}, None)
    failed = {f["itemIdentifier"] for f in out["batchItemFailures"]}
    assert failed == {"bad", "broken"}
    assert aws.get_item(Key={"event_id": "evt-good"}).get("Item")


def test_failure_injection_can_be_disabled(aws, monkeypatch):
    monkeypatch.setenv("ALLOW_FAILURE_INJECTION", "false")
    processor = load("processor")
    rec = sqs_record("m1", "evt-x", payload={"simulate_failure": True})
    assert processor.handler({"Records": [rec]}, None) == {"batchItemFailures": []}


# --- query ----------------------------------------------------------------

def put(table, event_id, event_type, created_at):
    table.put_item(
        Item={
            "event_id": event_id,
            "type": event_type,
            "created_at": created_at,
            "payload_json": json.dumps({"id": event_id}),
        }
    )


def test_query_get_one(aws):
    query = load("query")
    put(aws, "e1", "order.created", "2026-01-01T00:00:00")
    ok = query.handler({"routeKey": "GET /events/{event_id}", "pathParameters": {"event_id": "e1"}}, None)
    assert ok["statusCode"] == 200
    assert json.loads(ok["body"])["payload"] == {"id": "e1"}
    missing = query.handler({"routeKey": "GET /events/{event_id}", "pathParameters": {"event_id": "nope"}}, None)
    assert missing["statusCode"] == 404


def test_query_list_by_type_newest_first(aws):
    query = load("query")
    put(aws, "old", "order.created", "2026-01-01T00:00:00")
    put(aws, "new", "order.created", "2026-02-01T00:00:00")
    put(aws, "other", "user.signed_up", "2026-03-01T00:00:00")
    resp = query.handler({"routeKey": "GET /events", "queryStringParameters": {"type": "order.created"}}, None)
    body = json.loads(resp["body"])
    assert [e["event_id"] for e in body["events"]] == ["new", "old"]


def test_query_list_requires_type(aws):
    query = load("query")
    assert query.handler({"routeKey": "GET /events"}, None)["statusCode"] == 400
