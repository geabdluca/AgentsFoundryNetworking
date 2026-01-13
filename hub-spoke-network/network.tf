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

# Delegated Subnet for AI Foundry Managed VNet (if needed)
resource "azurerm_subnet" "spoke_delegated" {
  name                 = "snet-delegated"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.spoke_delegated_subnet_prefix]

  delegation {
    name = "aifoundry-delegation"
    service_delegation {
      name    = "Microsoft.MachineLearningServices/workspaces"
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

  # Ensure NSG and subnet are fully created before association
  depends_on = [
    azurerm_network_security_group.dns,
    azurerm_subnet.dns
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
