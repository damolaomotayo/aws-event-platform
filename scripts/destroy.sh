#!/usr/bin/env bash
# Tear everything down so nothing keeps costing money.
set -euo pipefail
cd "$(dirname "$0")/../terraform"

REGION="${AWS_REGION:-eu-west-1}"

terraform destroy -input=false -auto-approve -var "region=${REGION}"
echo "All resources destroyed."
