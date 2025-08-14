## Introduction
------------
This project is part of a Technical Challenge. The use case in question is the implementation of an agent using the Happy Robot platform to automate inbound carrier calls. Carriers call in to request loads. The system must authenticate them, match them to viable loads, and negotiate pricing automatically.
As part of the solution, I simulate a call as a carrier and speak to the agent I configured on the Happy Robot platform.

## Features & Objectives
------------
1. MC number verification via FMCSA API
2. Load search from Data (json file)
3. Automated pitch and counter-offer negotiation (up to 3 rounds)
4. Call classification (outcome + sentiment)
5. Metrics dashboard/report
6. Secure API with API key authentication
7. Containerization with Docker
8. AWS Cloud deployment

## Features & Objectives
------------
1. Backend: Python, FastAPI
2. Frontend/Dashboard: Streamlit
3. Database: SQLite (local implementation) / Postgres RDS (AWS deployment)
4. Deployment: Docker + AWS (Platform + CLIv2) + Terraform
5. External APIs: FMCSA verification, HappyRobot web call trigger
6. Security: API Key Auth, HTTPS

## Dependencies and Installation (Local Implementation)
----------------------------

1. Clone the repository to your local machine.

2. Install the required dependencies by running the following command:
   ```
   pip install -r requirements.txt
   ```

3. An FMCSA key is required for carrier verification. Add it to the `.env` file in the project directory.
   Create an internal api key as well to pass through Webhooks from the Happy Robot platform everytime an API request is made to your local endpoint.
```commandline
FMCSA_API_KEY=fmcsa-api-key
INTERNAL_API_KEY =internal-api-key
```

4. For having a local endpoint that can be used for making API requests from the Happy Robot platform, use ngrok. Get a free Authtoken from ngrok after installing it in your system.
```
ngrok config add-authtoken YOUR_AUTHTOKEN
ngrok http 8000
```
This gives you an endpoint which you can set in the Webhooks as the url for all the necessary API requests from the Happy Robot Platform.

5. Backend + Dashboard
backend.main → backend is the folder, main is the python file name.
app → the FastAPI instance inside main.py.
--reload → auto-reloads on code changes (dev mode).
--host 0.0.0.0 → makes it accessible to external services like ngrok.
--port 8000 → matches the ngrok tunnel command (ngrok http 8000).
```
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
   For Streamlit
   app.py is in the folder named dashboard. This renders the UI for the dashboard which includes charts and metrics for the sales calls.
```
streamlit run dashboard/app.py
```

## Containerization with Docker
----------------------------
This project ships with Docker configs for both services:
Backend API (FastAPI / Uvicorn) — built from Dockerfile.backend and exposes 8000
Metrics Dashboard (e.g., Streamlit) — built from Dockerfile.dashboard and exposes 8501

Prerequisites:
- Docker Desktop installed and running (Windows/macOS) or Docker Engine (Linux)
- Optional: .env file at repo root for secrets & config (e.g., API keys, DB URL).
  The docker-compose.yml typically loads this automatically if present.

```bash
# Build images for all services
docker compose build

# Start containers in the background
docker compose up -d

# View logs (all services)
docker compose logs -f

# OR view logs per service
docker compose logs -f backend
docker compose logs -f dashboard

# Stop containers
docker compose down

```

Expected URLs

- Backend API: http://localhost:8000 (mapped from container port 8000)

- Dashboard: http://localhost:8501 (mapped from container port 8501)

## Cloud Deploy (AWS)
----------------------------
API (FastAPI) + Dashboard (Streamlit) on ECS Fargate behind an ALB, data in RDS Postgres, DNS via Route 53, TLS via ACM.
Dev uses SQLite locally; AWS uses RDS via DATABASE_URL (Secrets Manager).

### Architecture

- ALB: HTTPS 443 (default → dashboard), path rule /api/* → API. HTTP 80 → redirect to HTTPS.
- ECS/Fargate: Two services: *-api-svc, *-dashboard-svc.
- RDS Postgres: Small public instance (POC), security-grouped to ECS tasks.
- Secrets Manager: DATABASE_URL (postgresql+psycopg2://...).
- Route 53: aayushai.com → ALB (A + AAAA alias). www → CNAME apex (optional).
- CORS: ALLOWED_ORIGINS env on API task: https://aayushai.com,https://www.aayushai.com.

### Prerequisites

- AWS CLI configured for us-east-1
- Terraform installed
- ECR repos created: hr-api, hr-dashboard
- ACM certificate for your domain (in us-east-1)
- Route 53 hosted zone for your domain
- My domain is aayushai.com

### Terraform – initialize & apply
```
:: In the terraform directory
terraform init -upgrade
terraform plan -out=tfplan
terraform apply tfplan
```

### Build, tag, and push images to ECR
```
:: ECR login
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <your-ecr-endpoint>

:: Create a timestamp tag (no spaces)
set TAG=v%DATE:~10,4%%DATE:~4,2%%DATE:~7,2%-%TIME:~0,2%%TIME:~3,2%
set TAG=%TAG: =0%

:: API image
docker build -f Dockerfile.backend -t hr-api:%TAG% .
docker tag hr-api:%TAG% <your-ecr-endpoint>/hr-api:%TAG%
docker push <your-ecr-endpoint>/hr-api:%TAG%

:: Dashboard image
docker build -f Dockerfile.dashboard -t hr-dashboard:%TAG% .
docker tag hr-dashboard:%TAG% <your-ecr-endpoint>/hr-dashboard:%TAG%
docker push <your-ecr-endpoint>/hr-dashboard:%TAG%

```

### ECS – redeploy services
```
:: Force a new deployment (same task def)
aws ecs update-service --cluster <ecs-cluster-name> --service *-api-svc --force-new-deployment --no-cli-pager
aws ecs update-service --cluster <ecs-cluster-name> --service *-dashboard-svc --force-new-deployment --no-cli-pager

:: Wait until stable
aws ecs wait services-stable --cluster <ecs-cluster-name> --services *-api-svc *-dashboard-svc --no-cli-pager
```

### ALB – HTTPS listener, path routing, and HTTP→HTTPS
Find ARNs you’ll need
```
:: Load balancer ARN
aws elbv2 describe-load-balancers --names fde-inbound-alb --query "LoadBalancers[0].LoadBalancerArn" --no-cli-pager

:: Target groups
aws elbv2 describe-target-groups --names fde-inbound-tg-api fde-inbound-tg-dash --query "TargetGroups[].{Name:TargetGroupName,Arn:TargetGroupArn}" --no-cli-pager

:: Verify HTTPS listener (443); if empty, create it
aws elbv2 describe-listeners --load-balancer-arn <LB_ARN> --query "Listeners[].{Port:Port,Arn:ListenerArn,Protocol:Protocol}" --no-cli-pager

```

Create HTTPS 443 listener (default → dashboard)
```
aws elbv2 create-listener --load-balancer-arn <LB_ARN> --protocol HTTPS --port 443 --certificates CertificateArn=<CERT_ARN> --default-actions Type=forward,TargetGroupArn=<DASH_TG_ARN> --no-cli-pager
```

Add /api/* rule on 443 → API target group
```
aws elbv2 create-rule --listener-arn <HTTPS_LISTENER_ARN> --priority 10 --conditions Field=path-pattern,Values="/api/*","/api" --actions Type=forward,TargetGroupArn=<API_TG_ARN> --no-cli-pager
```

Modify HTTP 80 to redirect → HTTPS 443
```
aws elbv2 modify-listener --listener-arn <HTTP_LISTENER_ARN> --default-actions Type=redirect,RedirectConfig={Protocol=HTTPS,Port=443,StatusCode=HTTP_301} --no-cli-pager
```

Verify listener rules
```
aws elbv2 describe-rules --listener-arn <HTTPS_LISTENER_ARN> --no-cli-pager --query "Rules[].{Priority:Priority,Conditions:Conditions,Actions:Actions}"
```

### Secrets Manager – DATABASE_URL (RDS connection)
```
aws secretsmanager get-secret-value --secret-id fde-inbound-DATABASE_URL --no-cli-pager
```
Format:
postgresql+psycopg2://<user>:<pass>@<rds-endpoint>:5432/<db_name>

### Health Checks and Logs
```
:: ALB target health
aws elbv2 describe-target-health --target-group-arn <API_TG_ARN> --no-cli-pager
aws elbv2 describe-target-health --target-group-arn <DASH_TG_ARN> --no-cli-pager

:: CloudWatch logs (change group as needed)
aws logs tail /ecs/fde-inbound-api --since 30m --no-cli-pager
aws logs tail /ecs/fde-inbound-dashboard --since 30m --no-cli-pager
```

### Troubleshooting
```
:: Which image is running?
aws ecs describe-task-definition --task-definition <TASK_DEF_ARN> --query "taskDefinition.containerDefinitions[0].image" --no-cli-pager

:: Which TG is default on 443?
aws elbv2 describe-listeners --load-balancer-arn <LB_ARN> --query "Listeners[?Port==`443`].DefaultActions" --no-cli-pager

:: Confirm path rule exists
aws elbv2 describe-rules --listener-arn <HTTPS_LISTENER_ARN> --no-cli-pager

:: Force replace a flapping task
aws ecs update-service --cluster fde-inbound-cluster --service fde-inbound-api-svc --force-new-deployment --no-cli-pager

```