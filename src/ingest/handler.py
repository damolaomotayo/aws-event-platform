"""Ingest Lambda: validate an HTTP request and publish it to EventBridge.

The API returns 202 Accepted as soon as EventBridge has the event. Actual
processing happens asynchronously, so a slow or failing downstream never
slows down or breaks the caller.
"""
import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# e.g. "order.created", "user.signed_up"
TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_BODY_BYTES = 100_000

_client = None


def _events():
    global _client
    if _client is None:
        _client = boto3.client("events")
    return _client


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event, context):
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8", errors="replace")

    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        return _response(413, {"error": "body too large"})

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _response(400, {"error": "body must be valid JSON"})

    if not isinstance(data, dict):
        return _response(400, {"error": "body must be a JSON object"})

    event_type = data.get("type")
    payload = data.get("payload", {})

    if not isinstance(event_type, str) or not TYPE_RE.match(event_type):
        return _response(400, {"error": "type must look like 'order.created'"})
    if not isinstance(payload, dict):
        return _response(400, {"error": "payload must be a JSON object"})

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    key = headers.get("idempotency-key")
    if key is not None and not KEY_RE.match(key):
        return _response(400, {"error": "Idempotency-Key must be 8-64 chars: letters, digits, _ or -"})

    # A client-supplied key makes retries safe: same key -> same event_id ->
    # the processor stores it only once.
    event_id = key or str(uuid.uuid4())

    detail = {
        "event_id": event_id,
        "type": event_type,
        "payload": payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = _events().put_events(
        Entries=[
            {
                "EventBusName": os.environ["EVENT_BUS_NAME"],
                "Source": "platform.ingest",
                "DetailType": event_type,
                "Detail": json.dumps(detail),
            }
        ]
    )

    if result.get("FailedEntryCount", 0) > 0:
        logger.error("EventBridge rejected event: %s", result["Entries"])
        return _response(502, {"error": "could not publish event, please retry"})

    logger.info("accepted event_id=%s type=%s", event_id, event_type)
    return _response(202, {"event_id": event_id, "status": "accepted"})
