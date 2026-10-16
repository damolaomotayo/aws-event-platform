# --- Packaging: zip each function's source directory ----------------------

data "archive_file" "ingest" {
  type        = "zip"
  source_dir  = "${path.module}/../src/ingest"
  output_path = "${path.module}/build/ingest.zip"
}

data "archive_file" "processor" {
  type        = "zip"
  source_dir  = "${path.module}/../src/processor"
  output_path = "${path.module}/build/processor.zip"
}

data "archive_file" "query" {
  type        = "zip"
  source_dir  = "${path.module}/../src/query"
  output_path = "${path.module}/build/query.zip"
}

# --- IAM: one least-privilege role per function ---------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  basic_execution = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role" "ingest" {
  name               = "${local.name}-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "ingest_logs" {
  role       = aws_iam_role.ingest.name
  policy_arn = local.basic_execution
}

resource "aws_iam_role_policy" "ingest" {
  name = "publish-events"
  role = aws_iam_role.ingest.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["events:PutEvents"]
      Resource = aws_cloudwatch_event_bus.main.arn
    }]
  })
}

resource "aws_iam_role" "processor" {
  name               = "${local.name}-processor"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "processor_logs" {
  role       = aws_iam_role.processor.name
  policy_arn = local.basic_execution
}

resource "aws_iam_role_policy" "processor" {
  name = "consume-queue-write-table"
  role = aws_iam_role.processor.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.main.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"]
        Resource = aws_dynamodb_table.events.arn
      }
    ]
  })
}

resource "aws_iam_role" "query" {
  name               = "${local.name}-query"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "query_logs" {
  role       = aws_iam_role.query.name
  policy_arn = local.basic_execution
}

resource "aws_iam_role_policy" "query" {
  name = "read-table"
  role = aws_iam_role.query.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["dynamodb:GetItem", "dynamodb:Query"]
      Resource = [
        aws_dynamodb_table.events.arn,
        "${aws_dynamodb_table.events.arn}/index/*"
      ]
    }]
  })
}

# --- Log groups (created explicitly so we control retention) --------------

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${local.name}-ingest"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "processor" {
  name              = "/aws/lambda/${local.name}-processor"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "query" {
  name              = "/aws/lambda/${local.name}-query"
  retention_in_days = var.log_retention_days
}

# --- Functions ------------------------------------------------------------
# Lambda runs your code in multiple AZs automatically, so there is no
# instance to fail over: if an AZ goes down, invocations land in another.

resource "aws_lambda_function" "ingest" {
  function_name    = "${local.name}-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      EVENT_BUS_NAME = aws_cloudwatch_event_bus.main.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest, aws_iam_role_policy_attachment.ingest_logs]
}

resource "aws_lambda_function" "processor" {
  function_name    = "${local.name}-processor"
  role             = aws_iam_role.processor.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.processor.output_path
  source_code_hash = data.archive_file.processor.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      TABLE_NAME              = aws_dynamodb_table.events.name
      ALLOW_FAILURE_INJECTION = tostring(var.enable_failure_injection)
    }
  }

  depends_on = [aws_cloudwatch_log_group.processor, aws_iam_role_policy_attachment.processor_logs]
}

resource "aws_lambda_function" "query" {
  function_name    = "${local.name}-query"
  role             = aws_iam_role.query.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.query.output_path
  source_code_hash = data.archive_file.query.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.events.name
      INDEX_NAME = "type-created-index"
    }
  }

  depends_on = [aws_cloudwatch_log_group.query, aws_iam_role_policy_attachment.query_logs]
}

# --- SQS -> processor -----------------------------------------------------

resource "aws_lambda_event_source_mapping" "processor" {
  event_source_arn                   = aws_sqs_queue.main.arn
  function_name                      = aws_lambda_function.processor.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 2

  # Only the failed messages in a batch are retried, not the whole batch.
  function_response_types = ["ReportBatchItemFailures"]

  # Cap concurrency so a burst cannot overwhelm downstream systems.
  scaling_config {
    maximum_concurrency = 10
  }
}
