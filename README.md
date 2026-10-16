# Highly Available Event-Driven AWS Platform

A serverless event pipeline on AWS, defined entirely in Terraform. Clients send events over HTTP; the platform accepts them instantly, routes them through EventBridge and SQS, processes them with Lambda, and stores them in DynamoDB. Failures retry automatically and end up in a dead-letter queue with alarms.

## Architecture

```
                         ┌────────────────────────── AWS region (multi-AZ) ──────────────────────────┐
                         │                                                                           │
 client ──POST /events──▶ API Gateway ──▶ ingest λ ──▶ EventBridge bus ──rule──▶ SQS queue ──▶ processor λ ──▶ DynamoDB
                         │ (HTTP API)    (validate)    (+ 7-day archive)          │  3 failed tries           (events table)
                         │                                                        ▼                              ▲
                         │                                                  Dead-letter queue                    │
 client ◀─GET /events───── API Gateway ──▶ query λ ─────────────────────────────────────────────────────────────┘
                         │
                         └─ CloudWatch alarms ──▶ SNS ──▶ email
```

## Why it is highly available

| Layer | HA mechanism |
|---|---|
| API Gateway, Lambda, EventBridge, SQS, DynamoDB | Managed services that run across multiple Availability Zones by default. No server to fail over. |
| Traffic spikes | SQS buffers bursts; processor concurrency is capped at 10 so downstream is never overwhelmed. API throttling protects the front door. |
| Transient failures | SQS retries each message up to 3 times. Only failed messages in a batch are retried (partial batch response). |
| Permanent failures | After 3 attempts the message moves to the DLQ (kept 14 days) and an alarm fires. |
| Duplicate delivery | Writes are idempotent (conditional put on `event_id`). Clients can send an `Idempotency-Key` header to make retries safe. |
| Data loss | DynamoDB point-in-time recovery, EventBridge archive for replay, encryption at rest everywhere. |
| Observability | Log groups with retention, API access logs, 4 CloudWatch alarms to SNS (DLQ not empty, queue backlog, processor errors, API 5xx). |

## Repo layout

```
terraform/   Infrastructure (data.tf, messaging.tf, lambda.tf, api.tf, monitoring.tf, ...)
src/         Lambda code: ingest/, processor/, query/
tests/       Unit tests (moto mocks AWS, no account needed)
scripts/     setup_ec2.sh, deploy.sh, smoke_test.py, destroy.sh
.github/     CI: tests + terraform fmt/validate
```

## Run it on your EC2 instance

Works on Amazon Linux 2023 or Ubuntu 22.04+. Run each line in order.

```bash
# 1. Attach an IAM role with AdministratorAccess to the instance (EC2 console: Actions > Security > Modify IAM role)

# 2. Get the code
git clone https://github.com/<you>/aws-event-platform.git && cd aws-event-platform

# 3. Install everything (git, python3, Terraform 1.9.8, AWS CLI v2, test deps) and check credentials
./scripts/setup_ec2.sh

# 4. Unit tests (no AWS resources created)
make test

# 5. Deploy (about 1-2 minutes)
export AWS_REGION=eu-west-1
make deploy

# 6. Prove it works
make smoke            # ~10 seconds, ends with "All N checks passed."
make smoke-dlq        # optional, ~2 minutes, proves the dead-letter queue

# 7. Try it by hand
API=$(terraform -chdir=terraform output -raw api_url)
curl -X POST "$API/events" -H 'content-type: application/json' -d '{"type":"order.created","payload":{"order_id":42}}'
curl "$API/events?type=order.created"

# 8. Tear down when finished (stops all cost)
make destroy
```

Optional: `export ALERT_EMAIL=you@example.com` before step 5 to get alarm emails (confirm the SNS email).

`make` is just a shortcut runner: each target in the `Makefile` wraps a command (`make deploy` runs `./scripts/deploy.sh`, which runs `terraform init` and `terraform apply`).

## API

| Method & path | Purpose |
|---|---|
| `POST /events` | Body `{"type": "order.created", "payload": {...}}`. Optional `Idempotency-Key` header. Returns `202` with `event_id`. |
| `GET /events/{event_id}` | Fetch one event. `404` if unknown. |
| `GET /events?type=X&limit=N` | Newest events of a type (limit 1-100, default 20). |

## Cost

Everything is pay-per-use. Idle cost is close to zero (DynamoDB on-demand, Lambda, SQS and EventBridge bill per request; CloudWatch logs and PITR have small storage charges). Running the smoke tests costs a fraction of a cent. Still run `make destroy` when you are done.

## Production hardening (deliberately left out of the demo)

- Authentication on the API (JWT authorizer, IAM auth or API keys)
- Remote Terraform state in S3 with DynamoDB locking
- Set `enable_failure_injection = false`
- Raise the SQS visibility timeout to 6x the Lambda timeout
- Multi-region failover (DynamoDB global tables, Route 53 health checks)
- Custom domain and WAF in front of the API
