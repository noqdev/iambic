variable "aws_region" {
  type        = string
  description = "The aws region in which the lambda function will be deployed"

  default = "us-west-2"
}

variable "target_account_id" {
  type = string
  description = "AWS account id of where the codebuild is deployed"
  # default = "1234567890"
  default = "442632209887"
}

variable "target_account_ecr_repo_name" {
  type        = string
  description = "Full name of the repo. In the context of ECR pull through cache, it's likely iambic-ecr-public/iambic/iambic"
  default = "iambic-ecr-public/iambic/iambic"
}

variable "target_iambic_image_tag" {
  type        = string
  description = "Tag of the image to be deployed"
  default = "latest"
}