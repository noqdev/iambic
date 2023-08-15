terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.9"
    }
  }
  required_version = ">= 1.2.0"
}

provider "aws" {
  region  = var.aws_region
  profile = var.profile_name
}

data "aws_caller_identity" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  lambda_function_name = "${var.lambda_function_name}${var.name_suffix}"
  api_gateway_name = "${var.api_gateway_name}${var.name_suffix}"
}


data "aws_ecr_repository" "iambic_private_ecr" {
  name = var.iambic_image_repo_name
}

data "aws_ecr_image" "iambic_private_ecr" {
  repository_name = data.aws_ecr_repository.iambic_private_ecr.name
  image_tag       = var.iambic_image_tag
}

data "aws_iam_role" "iambic_github_app_lambda_execution" {
  name = var.lambda_execution_role_name
}


resource "aws_lambda_function" "iambic_github_app" {
  image_uri     = "${data.aws_ecr_repository.iambic_private_ecr.repository_url}:${var.iambic_image_tag}"
  package_type  = "Image"
  function_name = local.lambda_function_name
  role          = data.aws_iam_role.iambic_github_app_lambda_execution.arn
  memory_size   = var.lambda_function_memory_size
  timeout       = var.lambda_function_timeout

  source_code_hash = trimprefix(data.aws_ecr_image.iambic_private_ecr.id, "sha256:")

  image_config {
    entry_point = ["python", "-m", "awslambdaric"]
    command = ["iambic.plugins.v0_1_0.github.github_app.run_handler"]
  }

  environment {
    variables =  {
      GITHUB_APP_SECRET_KEY_SECRET_ID     = var.github_app_private_key_secret_id
      GITHUB_APP_WEBHOOK_SECRET_SECRET_ID = var.github_webhook_secret_secret_id
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [
    data.aws_iam_role.iambic_github_app_lambda_execution,
    data.aws_ecr_repository.iambic_private_ecr,
  ]
}

resource "aws_lambda_function_url" "iambic_github_app" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 0 : 1
  function_name      = aws_lambda_function.iambic_github_app.function_name
  authorization_type = "NONE"
}

resource "aws_api_gateway_rest_api" "iambic" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 1 : 0
  name = local.api_gateway_name
  endpoint_configuration {
    types = ["REGIONAL"]
  }
  binary_media_types = [
    # This is a workaround to force VTL not to transform the request body
    "application/json",
  ]
}

resource "aws_api_gateway_method" "iambic" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 1 : 0
  authorization = "NONE"
  http_method   = "POST"
  resource_id   = aws_api_gateway_rest_api.iambic[0].root_resource_id
  rest_api_id   = aws_api_gateway_rest_api.iambic[0].id
}

resource "aws_api_gateway_integration" "iambic" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 1 : 0
  rest_api_id             = aws_api_gateway_rest_api.iambic[0].id
  resource_id             = aws_api_gateway_rest_api.iambic[0].root_resource_id
  http_method             = aws_api_gateway_method.iambic[0].http_method
  integration_http_method = "POST"
  type                    = "AWS"
  uri                     = aws_lambda_function.iambic_github_app.invoke_arn
  passthrough_behavior    = "WHEN_NO_MATCH"
  content_handling        = "CONVERT_TO_TEXT"

  request_parameters = {
    "integration.request.header.X-Amz-Invocation-Type" = "'Event'"
  }

  request_templates = {
    "application/json" = <<EOF
{
  "headers": {
    #foreach($param in $input.params().header.keySet())
    "$param": "$util.escapeJavaScript($input.params().header.get($param))"
    #if($foreach.hasNext),#end
    #end
  },
  "method": "$context.httpMethod",
  "rawBody": "$util.escapeJavaScript($util.base64Decode($input.body))"
}
EOF
  }
}

resource "aws_api_gateway_method_response" "response_200" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.iambic[0].id
  resource_id = aws_api_gateway_rest_api.iambic[0].root_resource_id
  http_method = aws_api_gateway_method.iambic[0].http_method
  status_code = "200"
}

resource "aws_api_gateway_integration_response" "response_200" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.iambic[0].id
  resource_id = aws_api_gateway_rest_api.iambic[0].root_resource_id
  http_method = aws_api_gateway_method.iambic[0].http_method
  status_code = aws_api_gateway_method_response.response_200[0].status_code
}

resource "aws_api_gateway_deployment" "iambic" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.iambic[0].id

  triggers = {
    # NOTE: The configuration below will satisfy ordering considerations,
    #       but not pick up all future REST API changes. More advanced patterns
    #       are possible, such as using the filesha1() function against the
    #       Terraform configuration file(s) or removing the .id references to
    #       calculate a hash against whole resources. Be aware that using whole
    #       resources will show a difference after the initial implementation.
    #       It will stabilize to only change when resources change afterwards.
    redeployment = sha1(jsonencode([
      aws_api_gateway_rest_api.iambic[0].root_resource_id,
      aws_api_gateway_method.iambic[0].id,
      aws_api_gateway_integration.iambic[0].id,
      aws_api_gateway_integration.iambic[0].request_templates,
      aws_api_gateway_method_response.response_200[0].id,
      aws_api_gateway_integration_response.response_200[0].id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 1 : 0
  deployment_id = aws_api_gateway_deployment.iambic[0].id
  rest_api_id   = aws_api_gateway_rest_api.iambic[0].id
  stage_name    = var.api_gateway_stage_name
}

resource "aws_lambda_permission" "apigw_lambda" {
  count = var.use_api_gateway_insetad_of_lambda_functions_url ? 1 : 0
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.iambic_github_app.function_name
  principal     = "apigateway.amazonaws.com"

  # More: http://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-control-access-using-iam-policies-to-invoke-api.html
  source_arn = "arn:aws:execute-api:${var.aws_region}:${local.account_id}:${aws_api_gateway_rest_api.iambic[0].id}/*/*"
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  count         = 4
  statement_id  = "AllowExecutionFromCloudWatch${count.index}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.iambic_github_app.function_name
  principal     = "events.amazonaws.com"
  source_arn    = element([
    aws_cloudwatch_event_rule.import.arn,
    aws_cloudwatch_event_rule.expire.arn,
    aws_cloudwatch_event_rule.enforce.arn,
    aws_cloudwatch_event_rule.detect.arn
  ], count.index)
}

resource "aws_cloudwatch_event_rule" "import" {
  name                = "schedule-import"
  schedule_expression = var.import_schedule
}

resource "aws_cloudwatch_event_rule" "expire" {
  name                = "schedule-expire"
  schedule_expression = var.expire_schedule
}

resource "aws_cloudwatch_event_rule" "enforce" {
  name                = "schedule-enforce"
  schedule_expression = var.enforce_schedule
}

resource "aws_cloudwatch_event_rule" "detect" {
  name                = "schedule-detect"
  schedule_expression = var.detect_schedule
}

resource "aws_cloudwatch_event_target" "import" {
  rule      = aws_cloudwatch_event_rule.import.name
  target_id = "LambdaImportTarget"
  arn       = aws_lambda_function.iambic_github_app.arn
  input     = jsonencode({"command" : "import", "source": "EventBridgeCron"})
}

resource "aws_cloudwatch_event_target" "expire" {
  rule      = aws_cloudwatch_event_rule.expire.name
  target_id = "LambdaExpireTarget"
  arn       = aws_lambda_function.iambic_github_app.arn
  input     = jsonencode({"command" : "expire", "source": "EventBridgeCron"})
}

resource "aws_cloudwatch_event_target" "enforce" {
  rule      = aws_cloudwatch_event_rule.enforce.name
  target_id = "LambdaEnforceTarget"
  arn       = aws_lambda_function.iambic_github_app.arn
  input     = jsonencode({"command" : "enforce", "source": "EventBridgeCron"})
}

resource "aws_cloudwatch_event_target" "detect" {
  rule      = aws_cloudwatch_event_rule.detect.name
  target_id = "LambdaDetectTarget"
  arn       = aws_lambda_function.iambic_github_app.arn
  input     = jsonencode({"command" : "detect", "source": "EventBridgeCron"})
}
