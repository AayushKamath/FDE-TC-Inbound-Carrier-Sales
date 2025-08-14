

locals {
  # If create_rds = true, build a Postgres URL from RDS.
  # Else, use the DATABASE_URL provided in terraform.tfvars (e.g., sqlite:///./metrics.db for dev)
  app_database_url = var.create_rds ? "postgresql+psycopg2://${var.db_username}:${var.db_password}@${aws_db_instance.this[0].address}:${aws_db_instance.this[0].port}/${var.db_name}" : var.secrets.DATABASE_URL

  app_internal_api_key = var.secrets.INTERNAL_API_KEY
  app_fmcsa_api_key    = var.secrets.FMCSA_API_KEY
}

# DATABASE_URL (used by API + Dashboard)
resource "aws_secretsmanager_secret" "database_url" {
  name = "${var.project}-DATABASE_URL"
}

resource "aws_secretsmanager_secret_version" "database_url_version" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = local.app_database_url
}

# INTERNAL_API_KEY (match ecs.tf: aws_secretsmanager_secret.internal_api)
resource "aws_secretsmanager_secret" "internal_api" {
  name = "${var.project}-INTERNAL_API_KEY"
}

resource "aws_secretsmanager_secret_version" "internal_api_version" {
  secret_id     = aws_secretsmanager_secret.internal_api.id
  secret_string = local.app_internal_api_key
}

# FMCSA_API_KEY (match ecs.tf: aws_secretsmanager_secret.fmcsa_api)
resource "aws_secretsmanager_secret" "fmcsa_api" {
  name = "${var.project}-FMCSA_API_KEY"
}

resource "aws_secretsmanager_secret_version" "fmcsa_api_version" {
  secret_id     = aws_secretsmanager_secret.fmcsa_api.id
  secret_string = local.app_fmcsa_api_key
}
