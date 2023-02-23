variable "aws_region" {
  type = string
  description = "The aws region in which the lambda function will be deployed"

  default = "us-west-2"
}

variable "github_app_private_key_secret_id" {
  type = string
  description = "AWS Secret ID that contains the Github App private key"

  default = "dev/test-github-app-private-key"
}

variable "github_webhook_secret_secret_id" {
  type = string
  description = "AWS Secret ID that contains the Github App webhook secret"

  default = "dev/test-github-app-webhook-secret"
}