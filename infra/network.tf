
# Use default VPC and its public subnets (simple for POC)
data "aws_vpc" "default" {
  default = true
  count   = var.use_default_vpc ? 1 : 0
}

data "aws_subnets" "default_public" {
  count = var.use_default_vpc ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default[0].id]
  }
}

locals {
  public_subnets = var.use_default_vpc ? data.aws_subnets.default_public[0].ids : var.public_subnet_ids
}

# Security groups
resource "aws_security_group" "alb_sg" {
  name        = "${var.project}-alb-sg"
  description = "ALB security group"
  vpc_id      = var.use_default_vpc ? data.aws_vpc.default[0].id : null

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs_tasks_sg" {
  name        = "${var.project}-ecs-tasks-sg"
  description = "ECS tasks security group"
  vpc_id      = var.use_default_vpc ? data.aws_vpc.default[0].id : null

  # Allow incoming from ALB
  ingress {
  from_port       = 8000
  to_port         = 8000
  protocol        = "tcp"
  security_groups = [aws_security_group.alb_sg.id]
  }

  ingress {
  from_port       = 8501
  to_port         = 8501
  protocol        = "tcp"
  security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}



# Security Group for RDS: allow Postgres from ECS tasks SG
resource "aws_security_group" "rds_sg" {
  name        = "${var.project}-rds-sg"
  description = "Allow Postgres from ECS tasks"
  vpc_id      = var.use_default_vpc ? data.aws_vpc.default[0].id : var.vpc_id

  ingress {
    description     = "Postgres from ECS tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
