output "api_url" {
  description = "Base URL of the HTTP API."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "event_bus_name" {
  value = aws_cloudwatch_event_bus.main.name
}

output "table_name" {
  value = aws_dynamodb_table.events.name
}

output "queue_url" {
  value = aws_sqs_queue.main.id
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.id
}

output "region" {
  value = var.region
}
