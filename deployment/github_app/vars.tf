variable "aws_region" {
  type        = string
  description = "The aws region in which the lambda function will be deployed"

  default = "us-west-2"
}

variable "github_app_private_key_secret_id" {
  type        = string
  description = "AWS Secret ID that contains the Github App private key"

  default = "dev/github-app-private-key"
}

variable "github_webhook_secret_secret_id" {
  type        = string
  description = "AWS Secret ID that contains the Github App webhook secret"

  default = "dev/github-app-webhook-secret"
}

variable "iambic_public_repo_url" {
  type        = string
  description = "Iambic Public Repo URL"

  default = "public.ecr.aws/o4z3c2v2"
}

variable "iambic_image_name" {
  type        = string
  description = "Iambic Image Repo"

  default = "iambic"
}

variable "iambic_image_tag" {
  type        = string
  description = "Iambic Image Tag"

  default = "latest"
}
