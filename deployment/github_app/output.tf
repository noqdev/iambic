output "function_url" {
  value = aws_lambda_function_url.iambic_github_app[*].function_url
}

output "api_gateway_url" {
  value = aws_api_gateway_stage.prod[*].invoke_url
}