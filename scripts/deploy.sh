#!/usr/bin/env bash
# Deploy the whole platform. Optional env vars:
#   AWS_REGION   (default eu-west-1)
#   ALERT_EMAIL  (address that receives alarm emails)
set -euo pipefail
cd "$(dirname "$0")/../terraform"

REGION="${AWS_REGION:-eu-west-1}"
EMAIL="${ALERT_EMAIL:-}"

terraform init -input=false
terraform apply -input=false -auto-approve \
  -var "region=${REGION}" \
  -var "alert_email=${EMAIL}"

echo
terraform output
