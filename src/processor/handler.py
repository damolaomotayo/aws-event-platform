"""Processor Lambda: consume events from SQS and store them in DynamoDB.

Key reliability ideas:
  * Partial batch response: only failed messages are retried.
  * Idempotent writes: a conditional put makes duplicate delivery harmless
    (SQS and EventBridge are both at-least-once).
  * After 3 failed receives SQS moves the message to the dead-letter queue.
"""
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_table = None


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def _process(record):
    body = json.loads(record["body"])  # the EventBridge envelope
    detail = body["detail"]
    payload = detail.get("payload", {})

    # Lets us demonstrate the DLQ on demand. Disabled in production by
    # setting enable_failure_injection = false in Terraform.
    allow = os.environ.get("ALLOW_FAILURE_INJECTION", "false").lower() == "true"
    if allow and payload.get("simulate_failure") is True:
        raise RuntimeError("simulated failure requested by payload")

    item = {
        "event_id": detail["event_id"],
        "type": detail["type"],
        "created_at": detail["created_at"],
        "received_at": datetime.now(timezone.utc).isoformat(),
        # Stored as a JSON string: DynamoDB rejects Python floats, and we
        # do not need to query inside the payload.
        "payload_json": json.dumps(payload),
    }

    try:
        _get_table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(event_id)",
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info("duplicate event_id=%s ignored", detail["event_id"])
            return
        raise

    logger.info("stored event_id=%s type=%s", detail["event_id"], detail["type"])


def handler(event, context):
    failures = []
    for record in event["Records"]:
        try:
            _process(record)
        except Exception:
            logger.exception("failed messageId=%s", record["messageId"])
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
