variable "project_name" {
  description = "Nombre del proyecto"
  type        = string
  default     = "dynamic-pricing"
}

variable "environment" {
  description = "Ambiente de despliegue"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "Región AWS"
  type        = string
  default     = "us-east-1"
}

variable "db_password" {
  description = "Password de base de datos"
  type        = string
  sensitive   = true
}

variable "db_username" {
  description = "Usuario de base de datos"
  type        = string
  default     = "pricing_user"
}

variable "db_name" {
  description = "Nombre de la base de datos"
  type        = string
  default     = "dynamic_pricing"
}

variable "instance_type" {
  description = "Tipo de instancia EC2"
  type        = string
  default     = "t3.medium"
}
