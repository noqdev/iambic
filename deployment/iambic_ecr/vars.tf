variable "aws_region" {
  type        = string
  description = "The aws region in which the lambda function will be deployed"

  default = "us-west-2"
}

variable "manage_aws_ecr_pull_through_cache" {
  type = bool

  # Pull through cache rule may already exist in AWS account
  # If that's the case, you can change the value to false.
  description = "Have this terraform module manage pull through cache"

  default = true
}

variable "ecr_repository_prefix" {
  type        = string
  description = "Prefix to reach public ecr"

  default = "iambic-ecr-public"
}

variable "ecr_public_alias" {
  type        = string
  description = "alias from ECR public"
  default = "iambic"
}

variable "public_repo_name" {
  type        = string
  description = "Repo name under the ECR alias"
  default = "iambic"
}
