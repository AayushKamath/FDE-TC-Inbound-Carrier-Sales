
resource "aws_ecs_cluster" "this" {
  name = "${var.project}-cluster"
}

# ------------------------------------------------------------
# IAM: allow ECS task agent (execution role) + task role
# to read our three Secrets Manager values
# ------------------------------------------------------------
data "aws_iam_policy_document" "secrets_read" {
  statement {
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [
      aws_secretsmanager_secret.database_url.arn,
      aws_secretsmanager_secret.internal_api.arn,
      aws_secretsmanager_secret.fmcsa_api.arn
    ]
  }
}

resource "aws_iam_policy" "secrets_read" {
  name   = "${var.project}-secrets-read"
  policy = data.aws_iam_policy_document.secrets_read.json
}

# Attach to EXECUTION role (container agent pulls secrets at start)
resource "aws_iam_role_policy_attachment" "task_exec_secrets_attach" {
  role       = aws_iam_role.task_execution_role.name
  policy_arn = aws_iam_policy.secrets_read.arn
}

# Attach to TASK role (if app code ever needs secrets directly)
resource "aws_iam_role_policy_attachment" "task_role_secrets_attach" {
  role       = aws_iam_role.task_role.name
  policy_arn = aws_iam_policy.secrets_read.arn
}

# ------------------------------------------------------------
# Task Definition: API
# ------------------------------------------------------------
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  execution_role_arn       = aws_iam_role.task_execution_role.arn
  task_role_arn            = aws_iam_role.task_role.arn

  container_definitions = jsonencode([
    {
      name  = "api"
      image = "${aws_ecr_repository.api.repository_url}:${var.image_tags.api_tag}"

      portMappings = [
        {
          containerPort = var.container_ports.api_port
          hostPort      = var.container_ports.api_port
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "LOG_LEVEL", value = "info" }
      ]

      # Inject secrets from AWS Secrets Manager
      secrets = [
        { name = "INTERNAL_API_KEY", valueFrom = aws_secretsmanager_secret.internal_api.arn },
        { name = "FMCSA_API_KEY",    valueFrom = aws_secretsmanager_secret.fmcsa_api.arn },
        { name = "DATABASE_URL",     valueFrom = aws_secretsmanager_secret.database_url.arn }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "ecs"
        }
      }

      essential = true

      # Uses your FastAPI /healthz (set in terraform.tfvars -> healthchecks.api_path)
      healthCheck = {
        command     = ["CMD-SHELL", "curl -s http://localhost:${var.container_ports.api_port}${var.healthchecks.api_path} || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }
    }
  ])
}

# ------------------------------------------------------------
# Task Definition: Dashboard (Streamlit)
# ------------------------------------------------------------
resource "aws_ecs_task_definition" "dashboard" {
  family                   = "${var.project}-dashboard"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  execution_role_arn       = aws_iam_role.task_execution_role.arn
  task_role_arn            = aws_iam_role.task_role.arn

  container_definitions = jsonencode([
    {
      name  = "dashboard"
      image = "${aws_ecr_repository.dashboard.repository_url}:${var.image_tags.dashboard_tag}"

      portMappings = [
        {
          containerPort = var.container_ports.dashboard_port
          hostPort      = var.container_ports.dashboard_port
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "LOG_LEVEL", value = "info" }
      ]

      # Dashboard only needs DATABASE_URL
      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.dashboard.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "ecs"
        }
      }

      essential = true

      # Health check for Streamlit
      healthCheck = {
        command     = ["CMD-SHELL", "curl -s http://localhost:${var.container_ports.dashboard_port}${var.healthchecks.dashboard_path} || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }
    }
  ])
}

# ------------------------------------------------------------
# Services
# ------------------------------------------------------------
resource "aws_ecs_service" "api" {
  name            = "${var.project}-api-svc"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.public_subnets
    assign_public_ip = true
    security_groups  = [aws_security_group.ecs_tasks_sg.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.container_ports.api_port
  }

  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "dashboard" {
  name            = "${var.project}-dashboard-svc"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.dashboard.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.public_subnets
    assign_public_ip = true
    security_groups  = [aws_security_group.ecs_tasks_sg.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.dashboard.arn
    container_name   = "dashboard"
    container_port   = var.container_ports.dashboard_port
  }

  depends_on = [aws_lb_listener.http]
}
