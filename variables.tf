variable "environment" {
  description = "Deployment environment; must match the selected Terraform workspace."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Environment must be dev or prod."
  }
}

variable "location" {
  description = "Azure region permitted by this subscription's allowed-locations policy."
  type        = string
}

variable "project_name" {
  description = "Prefix for this dashboard's Azure resources."
  type        = string
  default     = "f1-dashboard"
}

variable "sku_name" {
  description = "F1 for free development, B1 for the production environment."
  type        = string

  validation {
    condition     = contains(["F1", "B1"], var.sku_name)
    error_message = "Use F1 or B1."
  }
}
