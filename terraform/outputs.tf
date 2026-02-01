output "webhook_url" {
  description = "LINE Webhook URL"
  value       = "${aws_apigatewayv2_api.webhook_api.api_endpoint}/webhook"
}

output "api_endpoint" {
  description = "API Gateway endpoint"
  value       = aws_apigatewayv2_api.webhook_api.api_endpoint
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.webhook.function_name
}
