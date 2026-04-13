# ============================================
# Hub Virtual Network
# ============================================

resource "azurerm_virtual_network" "hub" {
  name                = local.hub_vnet_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = [var.hub_vnet_address_space]
  dns_servers         = [cidrhost(var.hub_dns_subnet_prefix, 4)]

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "hub"
    }
  )
}

# Gateway Subnet (required name for VPN Gateway)
resource "azurerm_subnet" "gateway" {
  name                 = "GatewaySubnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.hub_gateway_subnet_prefix]
}

# DNS Subnet
resource "azurerm_subnet" "dns" {
  name                 = "snet-dns"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.hub_dns_subnet_prefix]
}

# ============================================
# Foundry Spoke Virtual Network
# ============================================

resource "azurerm_virtual_network" "spoke" {
  name                = local.spoke_vnet_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = [var.spoke_vnet_address_space]
  dns_servers         = [cidrhost(var.hub_dns_subnet_prefix, 4)]

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "foundry-spoke"
    }
  )
}

# Private Endpoints Subnet in Spoke
resource "azurerm_subnet" "spoke_private_endpoints" {
  name                 = "snet-privateendpoints"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.spoke_private_endpoints_subnet_prefix]
}

# APIM Subnet in Spoke (used when deploying Foundry + APIM option)
resource "azurerm_subnet" "spoke_apim" {
  name                 = "snet-apim"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.spoke_apim_subnet_prefix]
}

# Delegated Subnet for AI Foundry Agents (Microsoft.App/environments)
resource "azurerm_subnet" "spoke_delegated" {
  name                 = "snet-agents"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.spoke_delegated_subnet_prefix]

  delegation {
    name = "agents-delegation"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action"
      ]
    }
  }
}

# ============================================
# Network Security Groups
# ============================================

# NSG for DNS Subnet
resource "azurerm_network_security_group" "dns" {
  name                = "nsg-dns"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  # Allow DNS from VNets
  security_rule {
    name                       = "Allow-DNS-Inbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "53"
    source_address_prefixes    = [var.hub_vnet_address_space, var.spoke_vnet_address_space]
    destination_address_prefix = "*"
  }

  # Allow RDP for management (from VPN clients)
  security_rule {
    name                       = "Allow-RDP-VPN"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefixes    = var.vpn_client_address_pool
    destination_address_prefix = "*"
  }

  tags = merge(
    var.tags,
    {
      environment = var.environment
    }
  )
}

# Associate NSG with DNS Subnet
resource "azurerm_subnet_network_security_group_association" "dns" {
  subnet_id                 = azurerm_subnet.dns.id
  network_security_group_id = azurerm_network_security_group.dns.id

  # Ensure NSG, subnet, and peering are fully created before association
  # This prevents 429 throttling errors by spacing out operations
  depends_on = [
    azurerm_network_security_group.dns,
    azurerm_subnet.dns,
    azurerm_virtual_network_peering.hub_to_spoke,
    azurerm_virtual_network_peering.spoke_to_hub
  ]

  timeouts {
    create = "10m"
    read   = "5m"
    delete = "10m"
  }
}

# NSG for Private Endpoints Subnet
resource "azurerm_network_security_group" "spoke_private_endpoints" {
  name                = "nsg-spoke-privateendpoints"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  tags = merge(
    var.tags,
    {
      environment = var.environment
    }
  )
}

# Associate NSG with Private Endpoints Subnet
resource "azurerm_subnet_network_security_group_association" "spoke_private_endpoints" {
  subnet_id                 = azurerm_subnet.spoke_private_endpoints.id
  network_security_group_id = azurerm_network_security_group.spoke_private_endpoints.id

  # Ensure NSG and subnet are fully created before association
  depends_on = [
    azurerm_network_security_group.spoke_private_endpoints,
    azurerm_subnet.spoke_private_endpoints
  ]

  timeouts {
    create = "10m"
    read   = "5m"
    delete = "10m"
  }
}

# NSG for Agents Subnet (spoke delegated subnet – Microsoft.App/environments)
resource "azurerm_network_security_group" "agents" {
  name                = "nsg-spoke-agents"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  # ── Security rules (commented out - uncomment to add restrictions) ──
  #
  # # Allow intra-subnet traffic
  # security_rule {
  #   name                       = "Allow-Outbound-Self"
  #   priority                   = 100
  #   direction                  = "Outbound"
  #   access                     = "Allow"
  #   protocol                   = "Tcp"
  #   source_port_range          = "*"
  #   destination_port_range     = "443"
  #   source_address_prefix      = "VirtualNetwork"
  #   destination_address_prefix = var.spoke_delegated_subnet_prefix
  # }
  #
  # # Allow outbound HTTPS to private endpoints subnet
  # security_rule {
  #   name                       = "Allow-Outbound-To-PrivateEndpoints"
  #   priority                   = 200
  #   direction                  = "Outbound"
  #   access                     = "Allow"
  #   protocol                   = "Tcp"
  #   source_port_range          = "*"
  #   destination_port_range     = "443"
  #   source_address_prefix      = "VirtualNetwork"
  #   destination_address_prefix = var.spoke_private_endpoints_subnet_prefix
  # }
  #
  # # Deny all other outbound traffic
  # security_rule {
  #   name                       = "Deny-All-Outbound"
  #   priority                   = 4096
  #   direction                  = "Outbound"
  #   access                     = "Deny"
  #   protocol                   = "*"
  #   source_port_range          = "*"
  #   destination_port_range     = "*"
  #   source_address_prefix      = "*"
  #   destination_address_prefix = "*"
  # }
  #
  # # Deny all inbound traffic
  # security_rule {
  #   name                       = "Deny-All-Inbound"
  #   priority                   = 4096
  #   direction                  = "Inbound"
  #   access                     = "Deny"
  #   protocol                   = "*"
  #   source_port_range          = "*"
  #   destination_port_range     = "*"
  #   source_address_prefix      = "*"
  #   destination_address_prefix = "*"
  # }

  tags = merge(
    var.tags,
    {
      environment = var.environment
    }
  )
}

# Associate NSG with Agents Subnet
resource "azurerm_subnet_network_security_group_association" "agents" {
  subnet_id                 = azurerm_subnet.spoke_delegated.id
  network_security_group_id = azurerm_network_security_group.agents.id

  depends_on = [
    azurerm_network_security_group.agents,
    azurerm_subnet.spoke_delegated,
    azurerm_virtual_network_peering.hub_to_spoke,
    azurerm_virtual_network_peering.spoke_to_hub
  ]

  timeouts {
    create = "10m"
    read   = "5m"
    delete = "10m"
  }
}

# ============================================
# NSG for APIM Subnet
# ============================================
# Mandatory rules required for APIM internal VNet mode.
# Lives here (hub-spoke) because the subnet is owned here.
# Rules are always present; harmless if APIM is not deployed.
resource "azurerm_network_security_group" "apim" {
  name                = "nsg-snet-apim"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ## Inbound rules
  security_rule {
    name                       = "AllowAPIMManagement"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3443"
    source_address_prefix      = "ApiManagement"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "AllowAzureLoadBalancer"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "6390"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "AllowHTTPSInbound"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "VirtualNetwork"
  }

  ## Outbound rules required for APIM dependencies
  security_rule {
    name                       = "AllowStorageOutbound"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "Storage"
  }

  security_rule {
    name                       = "AllowSQLOutbound"
    priority                   = 110
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "1433"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "Sql"
  }

  security_rule {
    name                       = "AllowKeyVaultOutbound"
    priority                   = 120
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "AzureKeyVault"
  }

  security_rule {
    name                       = "AllowMonitorOutbound"
    priority                   = 130
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["443", "1886"]
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "AzureMonitor"
  }

  security_rule {
    name                       = "AllowEntraIDOutbound"
    priority                   = 140
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "AzureActiveDirectory"
  }

  tags = merge(
    var.tags,
    {
      environment = var.environment
    }
  )
}

# Associate NSG with APIM Subnet
resource "azurerm_subnet_network_security_group_association" "apim" {
  subnet_id                 = azurerm_subnet.spoke_apim.id
  network_security_group_id = azurerm_network_security_group.apim.id

  depends_on = [
    azurerm_network_security_group.apim,
    azurerm_subnet.spoke_apim,
  ]

  timeouts {
    create = "10m"
    read   = "5m"
    delete = "10m"
  }
}
