# ============================================
# Azure Private DNS Zones
# ============================================

# Create Private DNS Zones
resource "azurerm_private_dns_zone" "zones" {
  for_each = var.create_private_dns_zones ? var.private_dns_zones : {}

  name                = each.value
  resource_group_name = azurerm_resource_group.main.name

  tags = merge(
    var.tags,
    {
      environment = var.environment
      service     = each.key
    }
  )
}

# Link Private DNS Zones to Hub VNet
resource "azurerm_private_dns_zone_virtual_network_link" "hub" {
  for_each = var.create_private_dns_zones ? var.private_dns_zones : {}

  name                  = "link-${each.key}-to-hub"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.zones[each.key].name
  virtual_network_id    = azurerm_virtual_network.hub.id
  registration_enabled  = false

  tags = merge(
    var.tags,
    {
      environment = var.environment
    }
  )
}

# Link Private DNS Zones to Spoke VNet
resource "azurerm_private_dns_zone_virtual_network_link" "spoke" {
  for_each = var.create_private_dns_zones ? var.private_dns_zones : {}

  name                  = "link-${each.key}-to-spoke"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.zones[each.key].name
  virtual_network_id    = azurerm_virtual_network.spoke.id
  registration_enabled  = false

  tags = merge(
    var.tags,
    {
      environment = var.environment
    }
  )
}
