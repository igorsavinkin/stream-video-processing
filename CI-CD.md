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
