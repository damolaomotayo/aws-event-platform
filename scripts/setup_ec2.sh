#!/usr/bin/env bash
# One-time setup on a fresh EC2 instance (Amazon Linux 2023 or Ubuntu 22.04+).
# Installs git, unzip, python3, pip and Terraform. AWS CLI is checked, not installed.
set -euo pipefail

TF_VERSION="${TF_VERSION:-1.9.8}"

if command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y git unzip python3 python3-pip make
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y git unzip python3 python3-pip python3-venv make curl
else
  echo "Unsupported OS: install git, unzip, python3, pip, make manually." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64)  ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *) echo "Unsupported CPU: $(uname -m)" >&2; exit 1 ;;
esac

if ! command -v terraform >/dev/null 2>&1; then
  echo "Installing Terraform ${TF_VERSION} (${ARCH})..."
  TMP="$(mktemp -d)"
  curl -fsSL -o "${TMP}/tf.zip" \
    "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_${ARCH}.zip"
  unzip -q "${TMP}/tf.zip" -d "${TMP}"
  sudo install -m 0755 "${TMP}/terraform" /usr/local/bin/terraform
  rm -rf "${TMP}"
fi

terraform version | head -1

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI not found. Install it: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" >&2
  exit 1
fi
aws --version

echo
echo "Checking AWS credentials..."
if aws sts get-caller-identity >/dev/null 2>&1; then
  aws sts get-caller-identity
else
  echo "No working AWS credentials. Attach an IAM role to this instance (recommended) or run 'aws configure'." >&2
  exit 1
fi

echo "Setup complete."
