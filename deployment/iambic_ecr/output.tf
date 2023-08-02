
output "ecr_url" {
  value = aws_ecr_repository.iambic_pull_through_cache.repository_url
}