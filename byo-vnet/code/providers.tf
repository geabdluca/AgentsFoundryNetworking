# ============================================
# Provider Configuration - Single Subscription
# ============================================

provider "azapi" {
}

provider "azurerm" {
  features {}
  subscription_id     = var.subscription_id
  storage_use_azuread = true
}
