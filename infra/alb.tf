
resource "aws_lb" "app" {
  name               = "${var.project}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = local.public_subnets
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project}-tg-api"
  port        = var.container_ports.api_port
  protocol    = "HTTP"
  vpc_id      = var.use_default_vpc ? data.aws_vpc.default[0].id : null
  target_type = "ip"
  health_check {
    enabled  = true
    path     = var.healthchecks.api_path
    matcher  = "200-399"
    protocol = "HTTP"
  }
}

resource "aws_lb_target_group" "dashboard" {
  name        = "${var.project}-tg-dash"
  port        = var.container_ports.dashboard_port
  protocol    = "HTTP"
  vpc_id      = var.use_default_vpc ? data.aws_vpc.default[0].id : null
  target_type = "ip"
  health_check {
    enabled  = true
    path     = var.healthchecks.dashboard_path
    matcher  = "200-399"
    protocol = "HTTP"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.dashboard.arn
  }
}

# Path-based routing: /api/* -> API; default -> Dashboard
resource "aws_lb_listener_rule" "api_rule" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}
