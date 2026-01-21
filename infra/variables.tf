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
