# ============================================
# Resource Group Outputs
# ============================================

output "resource_group_name" {
  description = "The name of the AI Foundry + APIM resource group"
  value       = azurerm_resource_group.foundry.name
}

output "resource_group_id" {
  description = "The ID of the AI Foundry + APIM resource group"
  value       = azurerm_resource_group.foundry.id
}

# ============================================
# AI Foundry Outputs
# ============================================

output "ai_foundry_name" {
  description = "The name of the AI Foundry account"
  value       = azapi_resource.ai_foundry.name
}

output "ai_foundry_id" {
  description = "The ID of the AI Foundry account"
  value       = azapi_resource.ai_foundry.id
}

output "ai_foundry_endpoint" {
  description = "The endpoint of the AI Foundry account"
  value       = azapi_resource.ai_foundry.output.properties.endpoint
}

output "ai_foundry_project_name" {
  description = "The name of the AI Foundry project"
  value       = azapi_resource.ai_foundry_project.name
}

output "ai_foundry_project_id" {
  description = "The ID of the AI Foundry project"
  value       = azapi_resource.ai_foundry_project.id
}

# ============================================
# API Management Outputs
# ============================================

output "apim_name" {
  description = "The name of the API Management instance"
  value       = azurerm_api_management.apim.name
}

output "apim_gateway_url" {
  description = "The gateway URL of the API Management instance (internal VNet only)"
  value       = azurerm_api_management.apim.gateway_url
}

output "apim_private_ip" {
  description = "The private IP address of the API Management instance"
  value       = azurerm_api_management.apim.private_ip_addresses
}

# ============================================
# Supporting Resources Outputs
# ============================================

output "storage_account_name" {
  description = "The name of the storage account"
  value       = azurerm_storage_account.storage_account.name
}

output "cosmosdb_account_name" {
  description = "The name of the Cosmos DB account"
  value       = azurerm_cosmosdb_account.cosmosdb.name
}

output "ai_search_name" {
  description = "The name of the AI Search service"
  value       = azapi_resource.ai_search.name
}

# ============================================
# Hub-Spoke Network Reference
# ============================================

output "hub_spoke_vnet_id" {
  description = "The ID of the Spoke VNet (from hub-spoke-network)"
  value       = local.hub_spoke_vnet_id
}

output "hub_spoke_resource_group" {
  description = "The resource group of the hub-spoke network"
  value       = local.hub_spoke_resource_group
}
