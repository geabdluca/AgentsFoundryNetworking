# ============================================
# Subscription Configuration
# ============================================

variable "subscription_id" {
  description = "The Azure subscription ID"
  type        = string
}

# ============================================
# Hub-Spoke Remote State Configuration
# ============================================

variable "hub_spoke_state_path" {
  description = "Path to the terraform.tfstate file from the hub-spoke-network deployment"
  type        = string
  default     = "../../hub-spoke-network/code/terraform.tfstate"
}

# ============================================
# Resource Configuration
# ============================================

variable "resource_group_name" {
  description = "The name of the resource group to create for AI Foundry + APIM resources"
  type        = string
  default     = "rg-aifoundry-apim"
}

variable "location" {
  description = "The Azure region to deploy resources. Must match the hub-spoke-network location. Region must support AI Foundry Private Class A subnet (networkInjections) — validation is enforced at the hub-spoke level."
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., dev, test, prod)"
  type        = string
  default     = "lab"
}

variable "tags" {
  description = "A map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ============================================
# AI Foundry Configuration
# ============================================

variable "ai_foundry_name" {
  description = "The name of the AI Foundry account (leave empty to auto-generate)"
  type        = string
  default     = ""
}

variable "project_name" {
  description = "The name of the AI Foundry project"
  type        = string
  default     = "apim-agent-project"
}

# ============================================
# API Management Configuration
# ============================================

variable "apim_publisher_name" {
  description = "Publisher name for API Management (auto-populated from az account show by the launcher)"
  type        = string
  default     = "AI Foundry Publisher"
}

variable "apim_publisher_email" {
  description = "Publisher email for API Management (auto-populated from az account show by the launcher)"
  type        = string
  default     = "admin@example.com"
}

variable "apim_sku" {
  description = "SKU for API Management. Developer has no SLA but is cost-effective for labs."
  type        = string
  default     = "Developer"
  validation {
    condition     = contains(["Developer", "Standard", "Premium"], var.apim_sku)
    error_message = "APIM SKU must be Developer, Standard, or Premium for internal VNet integration."
  }
}
