# ============================================
# Subscription Configuration
# ============================================

variable "subscription_id" {
  description = "The Azure subscription ID"
  type        = string
}

# ============================================
# Network Configuration Mode
# ============================================
# Set use_hub_spoke = true to use the hub-spoke-network deployment
# Set use_hub_spoke = false and provide your own subnet/DNS zone IDs

variable "use_hub_spoke" {
  description = "Whether to use the hub-spoke-network deployment. If false, you must provide subnet and DNS zone IDs manually."
  type        = bool
  default     = true
}

# ============================================
# Hub-Spoke Remote State Configuration
# (Only used when use_hub_spoke = true)
# ============================================

variable "hub_spoke_state_path" {
  description = "Path to the terraform.tfstate file from the hub-spoke-network deployment"
  type        = string
  default     = "../../hub-spoke-network/code/terraform.tfstate"
}

# ============================================
# Custom VNet Configuration
# (Only used when use_hub_spoke = false)
# ============================================

variable "subnet_id_private_endpoints" {
  description = "The resource ID of the subnet for private endpoints (required if use_hub_spoke = false)"
  type        = string
  default     = null
}

variable "subnet_id_agents" {
  description = "The resource ID of the delegated subnet for AI Foundry agents - must be delegated to Microsoft.App/environments (required if use_hub_spoke = false)"
  type        = string
  default     = null
}

variable "private_dns_zone_ids" {
  description = "Map of private DNS zone IDs (required if use_hub_spoke = false). Keys: blob_storage, cosmos, search, cognitive, openai, ai_services"
  type        = map(string)
  default     = {}
}

# ============================================
# Resource Configuration
# ============================================

variable "resource_group_name" {
  description = "The name of the resource group to create for AI Foundry resources"
  type        = string
  default     = "rg-aifoundry-resources"
}

variable "location" {
  description = "The Azure region to deploy resources (should match your VNet region)"
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
