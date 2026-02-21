# CI/CD Pipeline (GitHub Actions → ECR → ECS/Fargate)

This document explains how our CI/CD pipeline works, what AWS resources it uses,
and how to operate and troubleshoot it.

## Overview

Goal: Automatically build a Docker image from this repo, push it to AWS ECR, and
deploy it to AWS ECS Fargate.

Pipeline flow:
1. Code pushed to `main` (or manual run) triggers GitHub Actions.
2. Actions builds the Docker image and pushes it to ECR.
3. Task definition is rendered with the new image URI.
4. ECS service deploys the task on Fargate.

## Architecture & Runtime

- ECR stores the Docker image.
- ECS Cluster (Fargate) runs the container.
- ECS Service keeps desired tasks running.
- CloudWatch Logs stores container logs.

The app runs inside a container that exposes port `8000`.

## Required AWS Resources (in `us-east-1`)

- ECR Repository ( `stream-ml-service`)
- ECS Cluster ( `emotional-parrot`)
- ECS Service ( `stream-ml-service-1`)
- ECS Task Definition (family: `stream-ml-service`)
- IAM user `github-actions` with ECR/ECS permissions
- Security group that allows inbound TCP `8000` from your IP (or from ALB)

## Required GitHub Secrets

Set these in Repo Settings → Secrets and variables → Actions → Secrets:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` (set to `us-east-1`)
- `ECR_REPOSITORY` (name only, e.g. `stream-ml-service`)
- `ECS_CLUSTER` (cluster name)
- `ECS_SERVICE` (service name)

## Workflow File

The workflow lives in `.github/workflows/ci-cd.yml`.

It:
- configures AWS credentials
- logs in to ECR
- builds + pushes the Docker image
- renders a task definition
- deploys it to ECS

## Task Definition Template

`infra/ecs-task-def.json` must have real values (no `REPLACE_ME`):

- `executionRoleArn`:
  `arn:aws:iam::<account-id>:role/ecsTaskExecutionRole`

- `image`:
  `<account-id>.dkr.ecr.us-east-1.amazonaws.com/<repo-name>:latest`

The workflow overwrites the image at deploy time, but a valid image URI must be
present.

## Triggering Deployments

Automatic:
- Any push to `main` triggers CI/CD.

Manual:
- In GitHub → Actions → `ci-cd` → Run workflow

## Where to See It Running

ECS:
- ECS → Cluster → Service → Tasks
- Events tab shows deploy history

Logs:
- CloudWatch Logs → `/ecs/stream-ml-service`

Security groups:
- ECS Task → Networking → Security groups
- Ensure inbound rule exists: TCP `8000` from your IP (or ALB SG)

## Common Issues & Fixes

1) ECR auth error
- Error: not authorized to perform `ecr:GetAuthorizationToken`
- Cause: IAM permissions boundary or missing permissions.
- Fix: remove boundary or allow required ECR actions.

2) Task definition not found
- Register a task definition before creating a service.

3) Task keeps stopping
- Check CloudWatch Logs.
- Verify container port is `8000` and env vars if needed.

4) Wrong region
- ECR, ECS, and `AWS_REGION` must all match.

## Optional: Use OIDC (No Long-Lived Keys)

For stronger security, replace access keys with GitHub OIDC + an IAM role.
This requires updating the workflow and creating an IAM role with trust for
GitHub.

## Useful AWS Console Links

- ECS Clusters: https://console.aws.amazon.com/ecs/home
- ECR Repositories: https://console.aws.amazon.com/ecr/repositories
- CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups

## Quick Checklist

- [ ] Secrets set in GitHub
- [ ] ECR repo exists in `us-east-1`
- [ ] ECS cluster + service exist
- [ ] Task definition registered
- [ ] Workflow green

## Application Load Balancer (ALB)

The entry point through the ALB is the DNS name of the load balancer. Use it without specifying a port (ALB listens on 80).

**Base URL**
`http://lb-simple-one-862930693.us-east-1.elb.amazonaws.com`

**Available endpoints**
- `/health` — health check
- `/docs` — Swagger UI
- `/predict` — POST for image upload
- `/stream` — SSE stream with predictions from RTSP

**Examples**
- Health check: `http://lb-simple-one-862930693.us-east-1.elb.amazonaws.com/health`
- API docs: `http://lb-simple-one-862930693.us-east-1.elb.amazonaws.com/docs`
- Predict: `POST http://lb-simple-one-862930693.us-east-1.elb.amazonaws.com/predict`

ALB redirects traffic from port 80 to port 8000 of the container, so no port is needed in the URL.

## Testing AWS Deployment with Local Video

If the application is running in AWS (e.g. via ECS or ALB) and your test videos are located on your local PC, you can use the following methods to test the endpoints.

### Method 1: Uploading a Single Frame to `/predict`

1. **Get the AWS API URL:**
   - If using an ALB, use its DNS name (e.g., `http://your-alb-name.us-east-1.elb.amazonaws.com`).
   - If not using an ALB, get the public IP of the ECS task:
     ```bash
     aws ecs list-tasks --cluster emotional-parrot
     aws ecs describe-tasks --cluster emotional-parrot --tasks <task-id>
     # Or check the AWS Console: ECS -> Tasks -> Networking -> Public IP
     ```

2. **Extract a frame from your local video (using FFmpeg):**
   ```bash
   ffmpeg -i "C:\path\to\your\video.mp4" -ss 00:00:01 -vframes 1 frame.jpg
   ```

3. **Upload the frame to the API:**
   ```bash
   curl -X POST "http://YOUR-AWS-URL/predict" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@frame.jpg"
   ```
   *(Alternatively, you can test this interactively by opening `http://YOUR-AWS-URL/docs` in your browser and using the Swagger UI to upload the frame).*

### Method 2: Streaming via `/stream` with a Local RTSP Server

1. **Start a local RTSP server from your video:**
   Use FFmpeg to create a continuous stream on your PC:
   ```bash
   ffmpeg -re -stream_loop -1 -i "C:\path\to\your\video.mp4" -c copy -f rtsp rtsp://localhost:8554/live
   ```

2. **Expose the stream to AWS:**
   If AWS cannot connect directly to your PC, you will need to establish a tunnel (e.g., using ngrok, Cloudflare Tunnel) or set up the RTSP server directly in AWS (e.g. upload your video to S3, run an EC2 instance with MediaMTX/FFmpeg, and use its internal IP in ECS).

3. **Configure AWS to read your stream:**
   Update the `rtsp_url` configuration variable in your ECS task definition or `config.yaml` to point to your public RTSP URL.

4. **Watch the results:**
   Open `tools/sse_viewer.html` locally and set the API URL to `http://YOUR-AWS-URL/stream`.
