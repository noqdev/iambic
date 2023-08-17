terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.9.0"
    }
  }
  required_version = ">= 1.2.0"
}

provider "aws" {
  region  = var.aws_region
  profile = var.profile_name
}


##########################
# ECR Pull Through Cache Section
###########################

resource "aws_ecr_pull_through_cache_rule" "ecr-public" {
  count = var.manage_aws_ecr_pull_through_cache ? 1 : 0
  ecr_repository_prefix = var.ecr_repository_prefix
  upstream_registry_url = "public.ecr.aws"
}

resource "aws_ecr_repository" "iambic_pull_through_cache" {
  name                 = "${var.ecr_repository_prefix}/${var.ecr_public_alias}/${var.public_repo_name}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

}

