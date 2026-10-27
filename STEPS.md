# STEPS: Highly Available Event-Driven AWS Platform

## Prerequisites (set these up BEFORE step 1)

| Need | Details |
|---|---|
| AWS account | A sandbox account you can create resources in (API Gateway, Lambda, IAM, EventBridge, SQS, DynamoDB, CloudWatch, SNS). |
| EC2 instance | Amazon Linux 2023 or Ubuntu 22.04+, **t3.small or bigger**, 8 GB disk, outbound internet. Inbound: SSH (port 22) from your IP only. |
| IAM role on the instance | Create a role with **AdministratorAccess** (sandbox only), then EC2 console → select instance → Actions → Security → Modify IAM role. No access keys needed. |
| SSH access | Your key pair `.pem` file, so you can connect: `ssh -i key.pem ec2-user@<public-ip>` (Ubuntu: `ubuntu@`). |
| The code on the instance | **Option A (private GitHub repo):** create a fine-grained token (GitHub → Settings → Developer settings → Fine-grained tokens), this repo only, **Contents: Read**. Use it as the password when `git clone` asks. **Option B (no GitHub):** from your laptop run `scp -i key.pem aws-event-platform.tar.gz ec2-user@<ip>:~` then on the instance `tar xzf aws-event-platform.tar.gz`. |
| Alert email (optional) | An address for CloudWatch alarm emails. |

Time: about 10 minutes. Cost: cents (everything is pay-per-use). Run step 7 when finished.

## Steps (run on the EC2 instance)

```bash
# 1. Get the code (Option A shown; for Option B just: cd aws-event-platform)
git clone https://github.com/<you>/aws-event-platform.git && cd aws-event-platform

# 2. Install Terraform 1.9.8, AWS CLI v2, Python test deps; checks the IAM role works
chmod +x scripts/setup_ec2.sh
./scripts/setup_ec2.sh

Create and attach role, aws sts get-caller-identity

# 3. Unit tests (creates nothing in AWS)
make test

# 4. Deploy (1-2 minutes)
export AWS_REGION=eu-west-1
export ALERT_EMAIL=you@example.com     # optional; confirm the SNS email afterwards
make deploy

# 5. Prove it works. Ends with "All N checks passed."
make smoke
make smoke-dlq          # optional, ~2 min, proves the dead-letter queue

# 6. Try it by hand
API=$(terraform -chdir=terraform output -raw api_url)
curl -X POST "$API/events" -H 'content-type: application/json' -d '{"type":"order.created","payload":{"order_id":42}}'
curl "$API/events?type=order.created"

# 7. Tear down (stops all cost)
make destroy
```

## If something goes wrong

| Symptom | Fix |
|---|---|
| `No working AWS credentials` in step 2 | The IAM role isn't attached to the instance. Attach it, wait 30 seconds, rerun. |
| `terraform: command not found` | Rerun `./scripts/setup_ec2.sh`. |
| Terraform error during `make deploy` | Copy the full error and send it to me. |
| `AccessDenied` during deploy | The role is missing permissions; use AdministratorAccess in a sandbox account. |
| Smoke test times out | Wait a minute and rerun `make smoke` (first Lambda starts are slow). |
