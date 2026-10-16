# DynamoDB is multi-AZ by design: every write is replicated across three
# Availability Zones before it is acknowledged. On-demand billing means no
# capacity planning and no cost when idle.
resource "aws_dynamodb_table" "events" {
  name         = "${local.name}-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }

  attribute {
    name = "type"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # Lets us list events of one type, newest first, without a table scan.
  global_secondary_index {
    name            = "type-created-index"
    hash_key        = "type"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}
