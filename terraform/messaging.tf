# --- EventBridge: the event backbone -------------------------------------

resource "aws_cloudwatch_event_bus" "main" {
  name = "${local.name}-bus"
}

# Archive every event so it can be replayed after a bug fix or outage.
resource "aws_cloudwatch_event_archive" "main" {
  name             = "${local.name}-archive"
  event_source_arn = aws_cloudwatch_event_bus.main.arn
  retention_days   = 7
}

# --- SQS: buffer + retry + dead-letter queue ------------------------------

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-events-dlq"
  message_retention_seconds = 1209600 # 14 days to investigate failures
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "main" {
  name = "${local.name}-events"

  # Must be >= the processor Lambda timeout. AWS recommends 6x; 30s keeps the
  # DLQ demo fast. Raise it for production workloads.
  visibility_timeout_seconds = 30
  message_retention_seconds  = 345600 # 4 days
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# --- Routing: EventBridge rule -> SQS --------------------------------------

resource "aws_cloudwatch_event_rule" "ingested" {
  name           = "${local.name}-ingested"
  event_bus_name = aws_cloudwatch_event_bus.main.name

  event_pattern = jsonencode({
    source = ["platform.ingest"]
  })
}

resource "aws_cloudwatch_event_target" "to_queue" {
  rule           = aws_cloudwatch_event_rule.ingested.name
  event_bus_name = aws_cloudwatch_event_bus.main.name
  target_id      = "events-queue"
  arn            = aws_sqs_queue.main.arn
}

# Only this specific rule may send to the queue.
resource "aws_sqs_queue_policy" "main" {
  queue_url = aws_sqs_queue.main.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridgeRule"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.main.arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.ingested.arn }
      }
    }]
  })
}
