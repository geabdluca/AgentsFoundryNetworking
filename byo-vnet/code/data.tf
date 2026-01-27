# ============================================
# Remote State Reference - Hub-Spoke Network
# ============================================
# Only used when use_hub_spoke = true
# Reads outputs from the hub-spoke-network deployment

data "terraform_remote_state" "hub_spoke" {
  count   = var.use_hub_spoke ? 1 : 0
  backend = "local"

  config = {
    path = var.hub_spoke_state_path
  }
}

# ============================================
# Current Azure Configuration
# ============================================

data "azurerm_client_config" "current" {}

# ============================================
# Local Values - Network Configuration
# ============================================
# These locals resolve the correct subnet/DNS IDs based on the mode

locals {
  # Subnet IDs
  subnet_id_private_endpoints = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.spoke_private_endpoints_subnet_id : var.subnet_id_private_endpoints
  subnet_id_agents            = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.spoke_delegated_subnet_id : var.subnet_id_agents

  # DNS Zone IDs
  dns_zone_blob_storage = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.private_dns_zone_ids["blob_storage"] : var.private_dns_zone_ids["blob_storage"]
  dns_zone_cosmos       = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.private_dns_zone_ids["cosmos"] : var.private_dns_zone_ids["cosmos"]
  dns_zone_search       = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.private_dns_zone_ids["search"] : var.private_dns_zone_ids["search"]
  dns_zone_cognitive    = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.private_dns_zone_ids["cognitive"] : var.private_dns_zone_ids["cognitive"]
  dns_zone_openai       = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.private_dns_zone_ids["openai"] : var.private_dns_zone_ids["openai"]
  dns_zone_ai_services  = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.private_dns_zone_ids["ai_services"] : var.private_dns_zone_ids["ai_services"]

  # Hub-spoke reference (for outputs)
  hub_spoke_resource_group = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.resource_group_name : "N/A - Custom VNet"
  hub_spoke_vnet_id        = var.use_hub_spoke ? data.terraform_remote_state.hub_spoke[0].outputs.spoke_vnet_id : "N/A - Custom VNet"
}
