variable "bucket_name" {
  description = "Name of the S3 bucket for Kubernetes logs"
  type        = string
  default     = "k8s-log-bucket"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}