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

  # uncomment the profile config if your terraform setup uses aws profile
  # profile = "YOUR_CONFIGURED_PROFILE"
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "iambic_code_build" {
  name               = "iambic_code_build"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "iambic_code_build" {
  statement {
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["*"]
  }

  statement {
    sid = "ecr"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:GetAuthorizationToken",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchImportUpstreamImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer"
    ]

    resources = ["*"]
  }

  statement {
    effect = "Allow"

    actions = [
      "codebuild:CreateReportGroup",
      "codebuild:CreateReport",
      "codebuild:UpdateReport",
      "codebuild:BatchPutTestCases",
      "codebuild:BatchPutCodeCoverages"
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "iambic_code_build" {
  role   = aws_iam_role.iambic_code_build.name
  policy = data.aws_iam_policy_document.iambic_code_build.json
}

data "local_file" "buildspec_local" {
    filename = "${path.module}/buildspec.yaml"
}

resource "aws_codebuild_project" "iambic_code_build" {
  name          = "iambic-code-build"
  description   = "iambic-code-build"
  build_timeout = "10"
  service_role  = aws_iam_role.iambic_code_build.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode = true # because we need to use docker

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = "${var.aws_region}"
    }

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = "${var.target_account_id}"
    }

    environment_variable {
      name  = "IMAGE_REPO_NAME"
      value = "${var.target_account_ecr_repo_name}"
    }

    environment_variable {
      name  = "IMAGE_TAG"
      value = "${var.target_iambic_image_tag}"
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = "log-group"
      stream_name = "log-stream"
    }
  }

  source {
    type            = "NO_SOURCE"
    buildspec       = data.local_file.buildspec_local.content
  }

  source_version = "master"

  tags = {
    Environment = "Test"
  }
}
