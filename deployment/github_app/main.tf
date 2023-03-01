terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.16"
    }
  }
  required_version = ">= 1.2.0"
}

provider "aws" {
  region  = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  ecr_image_tag = "latest"
}

resource "null_resource" "iambic_public_repo" {

  triggers = {
    always_run = "${timestamp()}"
  }

  depends_on = [
    aws_ecr_repository.iambic_private_ecr,
  ]

  provisioner "local-exec" {
    command = <<EOF
        docker logout ${var.iambic_public_repo_url}
        docker pull ${var.iambic_public_repo_url}/${var.iambic_image_name}:${var.iambic_image_tag}
        aws --profile ${var.aws_profile} ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${local.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com
        docker tag ${var.iambic_public_repo_url}/${var.iambic_image_name}:${var.iambic_image_tag} ${aws_ecr_repository.iambic_private_ecr.repository_url}:${local.ecr_image_tag}
        docker push ${aws_ecr_repository.iambic_private_ecr.repository_url}:${local.ecr_image_tag}

    EOF
  }
}

resource "aws_ecr_repository" "iambic_private_ecr" { #tfsec:ignore:aws-ecr-repository-customer-key
  name                 = "iambic_private_ecr"
  image_tag_mutability = "MUTABLE" #tfsec:ignore:aws-ecr-enforce-immutable-repository

  image_scanning_configuration {
    scan_on_push = true
  }
}

data "aws_ecr_image" "iambic_private_ecr" {
  repository_name = aws_ecr_repository.iambic_private_ecr.name
  image_tag       = local.ecr_image_tag

  depends_on = [
    null_resource.iambic_public_repo,
  ]

}

data "aws_iam_role" "iambic_github_app_lambda_execution" {
  name = "iambic_github_app_lambda_execution"
}


resource "aws_lambda_function" "iambic_github_app" {
  image_uri     = "${aws_ecr_repository.iambic_private_ecr.repository_url}:latest" # repo and tag
  package_type  = "Image"
  function_name = "iambic_github_app_webhook"
  role          = data.aws_iam_role.iambic_github_app_lambda_execution.arn
  memory_size   = 2048
  timeout       = 900

  source_code_hash = trimprefix(data.aws_ecr_image.iambic_private_ecr.id, "sha256:")

  image_config {
    entry_point = ["python", "-m", "awslambdaric"]
    command = ["iambic.plugins.v0_1_0.github.github_app.run_handler"]
  }

  environment {
    variables = {
      GITHUB_APP_SECRET_KEY_SECRET_ID     = var.github_app_private_key_secret_id
      GITHUB_APP_WEBHOOK_SECRET_SECRET_ID = var.github_webhook_secret_secret_id
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [
    data.aws_iam_role.iambic_github_app_lambda_execution,
    aws_ecr_repository.iambic_private_ecr,
    null_resource.iambic_public_repo,
  ]
}

resource "aws_lambda_function_url" "iambic_github_app" {
  function_name      = aws_lambda_function.iambic_github_app.function_name
  authorization_type = "NONE"
}
