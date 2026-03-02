variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "cluster_name" {
  type    = string
  default = "stream-ml-cluster"
}

variable "service_name" {
  type    = string
  default = "stream-ml-service"
}

variable "container_name" {
  type    = string
  default = "stream-ml-service"
}

variable "container_image" {
  type = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

# ---------------------------------------------------------------------------
# Autoscaling
# ---------------------------------------------------------------------------

variable "autoscaling_min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
  default     = 1
}

variable "autoscaling_max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
  default     = 4
}

variable "cpu_target_percent" {
  description = "Target CPU utilisation (%) for autoscaling"
  type        = number
  default     = 70
}

variable "memory_target_percent" {
  description = "Target memory utilisation (%) for autoscaling"
  type        = number
  default     = 75
}

variable "scale_in_cooldown" {
  description = "Cooldown (seconds) before scaling in"
  type        = number
  default     = 300
}

variable "scale_out_cooldown" {
  description = "Cooldown (seconds) before scaling out"
  type        = number
  default     = 60
}

# ---------------------------------------------------------------------------
# CPU / RAM guardrail alarms
# ---------------------------------------------------------------------------

variable "cpu_alarm_threshold" {
  description = "CPU % threshold for CloudWatch alarm"
  type        = number
  default     = 85
}

variable "memory_alarm_threshold" {
  description = "Memory % threshold for CloudWatch alarm"
  type        = number
  default     = 85
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for alarm notifications (empty = no notifications)"
  type        = string
  default     = ""
}
