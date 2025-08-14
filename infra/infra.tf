
# ECR repos
resource "aws_ecr_repository" "api" {
  name = var.ecr_api_repo_name
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "dashboard" {
  name = var.ecr_dashboard_repo_name
  image_scanning_configuration {
    scan_on_push = true
  }
}

# CloudWatch log groups
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-api"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "dashboard" {
  name              = "/ecs/${var.project}-dashboard"
  retention_in_days = 14
}

# IAM for ECS tasks
data "aws_iam_policy_document" "task_execution_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "task_execution_role" {
  name               = "${var.project}-task-exec-role"
  assume_role_policy = data.aws_iam_policy_document.task_execution_assume.json
}

resource "aws_iam_role_policy_attachment" "task_exec_policy_attach" {
  role       = aws_iam_role.task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task role for reading secrets
resource "aws_iam_role" "task_role" {
  name               = "${var.project}-task-role"
  assume_role_policy = data.aws_iam_policy_document.task_execution_assume.json
}





