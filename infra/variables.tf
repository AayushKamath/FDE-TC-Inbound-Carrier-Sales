
# Project / Region
variable "project" {
  description = "Name used in resource names (e.g., fde-inbound)"
  type        = string
  default     = "fde-inbound"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# ECR repo names (match your ecs.tf usage)
variable "ecr_api_repo_name" {
  description = "ECR repo for API image"
  type        = string
  default     = "hr-api"
}

variable "ecr_dashboard_repo_name" {
  description = "ECR repo for Dashboard image"
  type        = string
  default     = "hr-dashboard"
}

# Image tags used in ecs.tf
variable "image_tags" {
  description = "Container image tags"
  type = object({
    api_tag       : string
    dashboard_tag : string
  })
  default = {
    api_tag       = "latest"
    dashboard_tag = "latest"
  }
}

# Ports used in ecs.tf health checks and mappings
variable "container_ports" {
  description = "Container ports for API and Dashboard"
  type = object({
    api_port       : number
    dashboard_port : number
  })
  default = {
    api_port       = 8000
    dashboard_port = 8501
  }
}

# Health check paths (we added /healthz in FastAPI)
variable "healthchecks" {
  description = "Health check paths for ALB target groups"
  type = object({
    api_path       : string
    dashboard_path : string
  })
  default = {
    api_path       = "/healthz"
    dashboard_path = "/healthz"
  }
}

# ECS sizing
variable "desired_count" {
  description = "Number of tasks per service"
  type        = number
  default     = 1
}

variable "cpu" {
  description = "Fargate task CPU units"
  type        = number
  default     = 512
}

variable "memory" {
  description = "Fargate task memory (MiB)"
  type        = number
  default     = 1024
}

# Network toggle used by network.tf
variable "use_default_vpc" {
  description = "Use the default VPC if true; otherwise create/lookup custom VPC"
  type        = bool
  default     = true
}

# ---- RDS / Secrets (already in your setup; keeping for completeness) ----
variable "create_rds" {
  description = "Provision RDS Postgres and use it in AWS"
  type        = bool
  default     = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "RDS database name"
  type        = string
  default     = "metrics"
}

variable "db_username" {
  description = "RDS username"
  type        = string
  default     = "appuser"
}

variable "db_password" {
  description = "RDS password"
  type        = string
  sensitive   = true
  default     = "CHANGE_ME_STRONG"
}

# Legacy/dev secrets map (used by secrets.tf when create_rds=false)
variable "secrets" {
  description = "Dev/local secrets map (SQLite/db URL etc.)"
  type = object({
    INTERNAL_API_KEY : string
    FMCSA_API_KEY    : string
    DATABASE_URL     : string
  })
  default = {
    INTERNAL_API_KEY = "changeme-internal"
    FMCSA_API_KEY    = "changeme-fmcsa"
    DATABASE_URL     = "sqlite:///./metrics.db"
  }
}

# When NOT using the default VPC, provide explicit IDs here.
# Declaring them with safe defaults prevents compile-time errors.
variable "vpc_id" {
  description = "Existing VPC ID to deploy into (used when use_default_vpc = false)"
  type        = string
  default     = null
}

variable "public_subnet_ids" {
  description = "Public subnet IDs (when use_default_vpc = false)"
  type        = list(string)
  default     = []
}

variable "private_subnet_ids" {
  description = "Private subnet IDs (when use_default_vpc = false)"
  type        = list(string)
  default     = []
}

