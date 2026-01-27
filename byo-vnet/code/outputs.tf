# ============================================
# Resource Group Outputs
# ============================================

output "resource_group_name" {
  description = "The name of the AI Foundry resource group"
  value       = azurerm_resource_group.foundry.name
}

output "resource_group_id" {
  description = "The ID of the AI Foundry resource group"
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

output "ai_foundry_project_name" {
  description = "The name of the AI Foundry project"
  value       = azapi_resource.ai_foundry_project.name
}

output "ai_foundry_project_id" {
  description = "The ID of the AI Foundry project"
  value       = azapi_resource.ai_foundry_project.id
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
# Hub-Spoke Network Reference (from remote state)
# ============================================

output "hub_spoke_vnet_id" {
  description = "The ID of the Spoke VNet (from hub-spoke-network or N/A if custom)"
  value       = local.hub_spoke_vnet_id
}

output "hub_spoke_resource_group" {
  description = "The resource group of the hub-spoke network (or N/A if custom)"
  value       = local.hub_spoke_resource_group
}
