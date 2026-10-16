variable "project" {
  description = "Short name used as a prefix for every resource."
  type        = string
  default     = "event-platform"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "eu-west-1"
}

variable "alert_email" {
  description = "Email address for alarm notifications. Leave empty to skip the subscription."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention for Lambda and API logs."
  type        = number
  default     = 14
}

variable "api_throttle_rate" {
  description = "Steady-state requests per second allowed by the API."
  type        = number
  default     = 50
}

variable "api_throttle_burst" {
  description = "Burst request limit for the API."
  type        = number
  default     = 100
}

variable "enable_failure_injection" {
  description = "If true, events with payload.simulate_failure=true make the processor fail (used to demo the DLQ). Turn off in production."
  type        = bool
  default     = true
}
