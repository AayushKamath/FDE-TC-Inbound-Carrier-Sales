# NOTE: For a quick POC, we create a small public RDS. For production, move to private subnets.

# Subnet group for RDS
resource "aws_db_subnet_group" "this" {
  count      = var.create_rds ? 1 : 0
  name       = "${var.project}-db-subnet-group"
  subnet_ids = local.public_subnets
}

# Postgres instance
resource "aws_db_instance" "this" {
  count                 = var.create_rds ? 1 : 0
  identifier            = "${var.project}-pg"
  engine                = "postgres"
  engine_version        = "16.3"
  instance_class        = var.db_instance_class
  allocated_storage     = 20
  db_name               = var.db_name
  username              = var.db_username
  password              = var.db_password                  # <<< use the var (matches Secrets)
  db_subnet_group_name  = aws_db_subnet_group.this[0].name
  publicly_accessible   = true
  skip_final_snapshot   = true

  # IMPORTANT: allow ECS tasks to reach Postgres (created below in network.tf)
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
}
