# ============================================
# Remote State Reference - Hub-Spoke Network
# ============================================
# Reads outputs from the hub-spoke-network deployment

data "terraform_remote_state" "hub_spoke" {
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

locals {
  # Subnet IDs (from hub-spoke remote state)
  subnet_id_private_endpoints = data.terraform_remote_state.hub_spoke.outputs.spoke_private_endpoints_subnet_id
  subnet_id_agents            = data.terraform_remote_state.hub_spoke.outputs.spoke_delegated_subnet_id
  subnet_id_apim              = data.terraform_remote_state.hub_spoke.outputs.spoke_apim_subnet_id

  # DNS Zone IDs (from hub-spoke remote state)
  dns_zone_blob_storage = data.terraform_remote_state.hub_spoke.outputs.private_dns_zone_ids["blob_storage"]
  dns_zone_cosmos       = data.terraform_remote_state.hub_spoke.outputs.private_dns_zone_ids["cosmos"]
  dns_zone_search       = data.terraform_remote_state.hub_spoke.outputs.private_dns_zone_ids["search"]
  dns_zone_cognitive    = data.terraform_remote_state.hub_spoke.outputs.private_dns_zone_ids["cognitive"]
  dns_zone_openai       = data.terraform_remote_state.hub_spoke.outputs.private_dns_zone_ids["openai"]
  dns_zone_ai_services  = data.terraform_remote_state.hub_spoke.outputs.private_dns_zone_ids["ai_services"]

  # Hub-spoke reference (for outputs)
  hub_spoke_resource_group = data.terraform_remote_state.hub_spoke.outputs.resource_group_name
  hub_spoke_vnet_id        = data.terraform_remote_state.hub_spoke.outputs.spoke_vnet_id

  # Project ID GUID (formatted from internal ID)
  project_id_guid = "${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 0, 8)}-${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 8, 4)}-${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 12, 4)}-${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 16, 4)}-${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 20, 12)}"
}
