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

data "aws_iam_role" "iambic_hub_role" {
  name = var.iambic_hub_role_name
}

resource "aws_iam_role" "iambic_github_app_lambda_execution" {
  name = var.iambic_github_app_lambda_execution_role_name

  # Terraform's "jsonencode" function converts a
  # Terraform expression result to valid JSON syntax.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = ""
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      },
    ]
  })

    inline_policy {
    name = "github-app"

    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Action   = [
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents"
          ]
          Effect   = "Allow"
          Resource = "*"
        },
        {
          Action   = [
            "secretsmanager:GetSecretValue",
          ]
          Effect   = "Allow"
          Resource = [
            "arn:aws:secretsmanager:*:*:secret:iambic/github-app-private-key-*",
            "arn:aws:secretsmanager:*:*:secret:iambic/github-app-webhook-secret-*",
            "arn:aws:secretsmanager:*:*:secret:iambic/github-app-secrets-*",
          ]
        },
        {
          Action   = [
            "sts:AssumeRole",
          ]
          Effect   = "Allow"
          Resource = [
            var.iambic_hub_role_arn,
          ]
        }
      ]
    })
  }
}