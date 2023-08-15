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

variable "name_suffix" {
  type = string
  description = "useful for testing to append suffix to resource names"
  default = ""
}

variable "use_api_gateway_insetad_of_lambda_functions_url" {
  type = bool
  description = "Use API Gateway instead of lambda functions url"
  default = false
}

variable "lambda_function_name" {
  type = string
  description = "function name for iambic"
  default = "iambic_github_app_webhook"
}

variable "lambda_function_memory_size" {
  type = number
  description = "amount of memory in megabytes"
  default = 2048
}

variable "lambda_function_timeout" {
  type = number
  description = "number of seconds before timeout"
  default = 900
}

variable "lambda_execution_role_name" {
  type = string
  description = "execution role name for the lambda function"
  default = "iambic_github_app_lambda_execution"
}

variable "api_gateway_name" {
  type = string
  description = "api gateway name for iambic"
  default = "iambic"
}

variable "api_gateway_stage_name" {
  type = string
  description = "api gateway stage for iambic"
  default = "prod"
}

variable "github_app_private_key_secret_id" {
  type        = string
  description = "AWS Secret ID that contains the Github App private key"

  default = "iambic/github-app-private-key"
}

variable "github_webhook_secret_secret_id" {
  type        = string
  description = "AWS Secret ID that contains the Github App webhook secret"

  default = "iambic/github-app-webhook-secret"
}

variable "iambic_image_repo_name" {
  type = string
  description = "ECR image uri holding the iambic image"
  default =  "iambic-ecr-public/iambic/iambic"
}

variable "iambic_image_tag" {
  type        = string
  description = "Iambic Image Tag"

  default = "latest"
}

variable "import_schedule" {
  description = "Cron expression for the import job"
  default     = "0 */2 * * *"
}

variable "expire_schedule" {
  description = "Cron expression for the expire job"
  default     = "5 * * * *"
}

variable "enforce_schedule" {
  description = "Cron expression for the enforce job"
  default     = "0 * * * *"
}

variable "detect_schedule" {
  description = "Cron expression for the detect job"
  default     = "*/5 * * * *"
}

variable "git_provider" {
  description = "Git provider (e.g., github, gitlab, bitbucket)"
  type        = string
}

variable "github_app_id" {
  description = "GitHub App ID"
  type        = string
  default     = ""
}

variable "github_installation_id" {
  description = "GitHub Installation ID"
  type        = string
  default     = ""
}

variable "repository_clone_url" {
  description = "Repository clone URL"
  type        = string
  default     = ""
}

variable "repository_full_name" {
  description = "Repository full name"
  type        = string
  default     = ""
}