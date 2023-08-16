variable "aws_region" {
  type        = string
  description = "The aws region in which the lambda function will be deployed"

  default = "us-west-2"
}

variable "profile_name" {
  type = string
  description = "aws profile for provider"
  default = ""
}

variable "iambic_hub_role_name" {
  type = string
  description = "IambicHubRole name"
  default = "IambicHubRole"
}

variable "iambic_hub_role_arn" {
  type = string
  description = "IambicHubRole name"
  default = "arn:aws:iam::760065561336:role/IambicHubRole"
}

variable "iambic_github_app_lambda_execution_role_name" {
  type = string
  description = "iambic_github_app_lambda_execution role name"
  default = "iambic_github_app_lambda_execution"
}
