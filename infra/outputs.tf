
output "alb_dns_name" {
  value = aws_lb.app.dns_name
}

output "api_ecr_url" {
  value = aws_ecr_repository.api.repository_url
}

output "dashboard_ecr_url" {
  value = aws_ecr_repository.dashboard.repository_url
}
