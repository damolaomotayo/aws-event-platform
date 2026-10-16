"""Query Lambda: read stored events back out of DynamoDB.

  GET /events/{event_id}          -> one event
  GET /events?type=X&limit=N      -> newest events of one type
"""
import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_table = None


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _public(item):
    return {
        "event_id": item["event_id"],
        "type": item["type"],
        "created_at": item["created_at"],
        "received_at": item.get("received_at"),
        "payload": json.loads(item.get("payload_json", "{}")),
    }


def handler(event, context):
    route = event.get("routeKey", "")

    if route == "GET /events/{event_id}":
        event_id = (event.get("pathParameters") or {}).get("event_id", "")
        found = _get_table().get_item(Key={"event_id": event_id}).get("Item")
        if not found:
            return _response(404, {"error": "event not found"})
        return _response(200, _public(found))

    if route == "GET /events":
        params = event.get("queryStringParameters") or {}
        event_type = params.get("type")
        if not event_type:
            return _response(400, {"error": "query parameter 'type' is required"})
        try:
            limit = max(1, min(int(params.get("limit", 20)), 100))
        except ValueError:
            return _response(400, {"error": "limit must be an integer"})

        result = _get_table().query(
            IndexName=os.environ["INDEX_NAME"],
            KeyConditionExpression=Key("type").eq(event_type),
            ScanIndexForward=False,  # newest first
            Limit=limit,
        )
        items = [_public(i) for i in result.get("Items", [])]
        return _response(200, {"count": len(items), "events": items})

    return _response(404, {"error": "route not found"})
