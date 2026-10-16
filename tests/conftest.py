import importlib.util
import pathlib

import boto3
import pytest
from moto import mock_aws

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLE = "test-events"
INDEX = "type-created-index"
BUS = "test-bus"


def load(name):
    """Import src/<name>/handler.py as a fresh module (all three are called handler.py)."""
    spec = importlib.util.spec_from_file_location(f"{name}_handler", ROOT / "src" / name / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def aws(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("TABLE_NAME", TABLE)
    monkeypatch.setenv("INDEX_NAME", INDEX)
    monkeypatch.setenv("EVENT_BUS_NAME", BUS)
    monkeypatch.setenv("ALLOW_FAILURE_INJECTION", "true")

    with mock_aws():
        boto3.client("events").create_event_bus(Name=BUS)
        ddb = boto3.resource("dynamodb")
        table = ddb.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "event_id", "AttributeType": "S"},
                {"AttributeName": "type", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": INDEX,
                    "KeySchema": [
                        {"AttributeName": "type", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        yield table
