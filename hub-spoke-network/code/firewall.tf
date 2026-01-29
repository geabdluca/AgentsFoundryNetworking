# ============================================
# Azure Firewall (Optional)
# ============================================

# Azure Firewall Subnet (must be named AzureFirewallSubnet)
resource "azurerm_subnet" "firewall" {
  count                = var.deploy_firewall ? 1 : 0
  name                 = "AzureFirewallSubnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.hub_firewall_subnet_prefix]
}

# Public IP for Azure Firewall
resource "azurerm_public_ip" "firewall" {
  count               = var.deploy_firewall ? 1 : 0
  name                = "pip-fw-${var.environment}-${var.location}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "firewall"
    }
  )
}

# ============================================
# Firewall Policy with Allow All Rules
# ============================================

resource "azurerm_firewall_policy" "main" {
  count               = var.deploy_firewall ? 1 : 0
  name                = "fwpol-${var.environment}-${var.location}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"

  tags = merge(
    var.tags,
    {
      environment = var.environment
    }
  )
}

# Firewall Policy Rule Collection Group
resource "azurerm_firewall_policy_rule_collection_group" "main" {
  count              = var.deploy_firewall ? 1 : 0
  name               = "rcg-allow-all"
  firewall_policy_id = azurerm_firewall_policy.main[0].id
  priority           = 100

  # Network Rule Collection - Allow All
  network_rule_collection {
    name     = "nrc-allow-all"
    priority = 100
    action   = "Allow"

    rule {
      name                  = "allow-all-outbound"
      protocols             = ["Any"]
      source_addresses      = ["*"]
      destination_addresses = ["*"]
      destination_ports     = ["*"]
    }
  }

  # Application Rule Collection - Allow All
  application_rule_collection {
    name     = "arc-allow-all"
    priority = 200
    action   = "Allow"

    rule {
      name = "allow-all-http-https"
      protocols {
        type = "Http"
        port = 80
      }
      protocols {
        type = "Https"
        port = 443
      }
      source_addresses  = ["*"]
      destination_fqdns = ["*"]
    }
  }
}

# ============================================
# Azure Firewall
# ============================================

resource "azurerm_firewall" "main" {
  count               = var.deploy_firewall ? 1 : 0
  name                = "fw-${var.environment}-${var.location}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = "AZFW_VNet"
  sku_tier            = "Standard"
  firewall_policy_id  = azurerm_firewall_policy.main[0].id

  ip_configuration {
    name                 = "fw-ipconfig"
    subnet_id            = azurerm_subnet.firewall[0].id
    public_ip_address_id = azurerm_public_ip.firewall[0].id
  }

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "firewall"
    }
  )
}

# ============================================
# Log Analytics Workspace for Firewall Diagnostics
# ============================================

resource "azurerm_log_analytics_workspace" "firewall" {
  count               = var.deploy_firewall ? 1 : 0
  name                = "log-fw-${var.environment}-${var.location}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "firewall-diagnostics"
    }
  )
}

# Diagnostic Settings for Azure Firewall
resource "azurerm_monitor_diagnostic_setting" "firewall" {
  count                      = var.deploy_firewall ? 1 : 0
  name                       = "diag-fw-${var.environment}"
  target_resource_id         = azurerm_firewall.main[0].id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.firewall[0].id

  # Azure Firewall Logs
  enabled_log {
    category = "AzureFirewallApplicationRule"
  }

  enabled_log {
    category = "AzureFirewallNetworkRule"
  }

  enabled_log {
    category = "AzureFirewallDnsProxy"
  }

  enabled_log {
    category = "AZFWNetworkRule"
  }

  enabled_log {
    category = "AZFWApplicationRule"
  }

  enabled_log {
    category = "AZFWNatRule"
  }

  enabled_log {
    category = "AZFWThreatIntel"
  }

  enabled_log {
    category = "AZFWIdpsSignature"
  }

  enabled_log {
    category = "AZFWDnsQuery"
  }

  enabled_log {
    category = "AZFWFqdnResolveFailure"
  }

  enabled_log {
    category = "AZFWFatFlow"
  }

  enabled_log {
    category = "AZFWFlowTrace"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

# ============================================
# Route Table for Agents Subnet (via Firewall)
# ============================================

resource "azurerm_route_table" "agents" {
  count               = var.deploy_firewall ? 1 : 0
  name                = "rt-agents-${var.environment}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  # Disable BGP route propagation to ensure traffic goes through firewall
  bgp_route_propagation_enabled = false

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "agents-routing"
    }
  )
}

# Default route to Azure Firewall
resource "azurerm_route" "agents_to_firewall" {
  count                  = var.deploy_firewall ? 1 : 0
  name                   = "route-to-firewall"
  resource_group_name    = azurerm_resource_group.main.name
  route_table_name       = azurerm_route_table.agents[0].name
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = azurerm_firewall.main[0].ip_configuration[0].private_ip_address
}

# Associate Route Table with Agents Subnet
resource "azurerm_subnet_route_table_association" "agents" {
  count          = var.deploy_firewall ? 1 : 0
  subnet_id      = azurerm_subnet.spoke_delegated.id
  route_table_id = azurerm_route_table.agents[0].id

  depends_on = [
    azurerm_firewall.main,
    azurerm_route.agents_to_firewall
  ]
}
