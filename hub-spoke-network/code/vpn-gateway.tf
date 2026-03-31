# ============================================
# Point-to-Site VPN Gateway
# ============================================

# Public IP for VPN Gateway
resource "azurerm_public_ip" "vpn_gateway" {
  name                = "pip-vpn-gateway-${local.resource_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "vpn-gateway"
    }
  )
}

# Generate Root Certificate for Certificate-based Authentication
resource "tls_private_key" "vpn_root_ca" {
  count     = var.vpn_auth_type == "Certificate" ? 1 : 0
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "tls_self_signed_cert" "vpn_root_ca" {
  count           = var.vpn_auth_type == "Certificate" ? 1 : 0
  private_key_pem = tls_private_key.vpn_root_ca[0].private_key_pem

  subject {
    common_name  = var.vpn_root_cert_name
    organization = "Azure AI Foundry Hub-Spoke"
  }

  validity_period_hours = 87600 # 10 years
  is_ca_certificate     = true

  allowed_uses = [
    "cert_signing",
    "crl_signing",
    "digital_signature",
    "key_encipherment",
  ]
}

# Generate Client Certificate signed by Root CA
resource "tls_private_key" "vpn_client" {
  count     = var.vpn_auth_type == "Certificate" ? 1 : 0
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_cert_request" "vpn_client" {
  count           = var.vpn_auth_type == "Certificate" ? 1 : 0
  private_key_pem = tls_private_key.vpn_client[0].private_key_pem

  subject {
    common_name  = var.vpn_client_cert_name
    organization = "Azure AI Foundry Hub-Spoke"
  }
}

resource "tls_locally_signed_cert" "vpn_client" {
  count                 = var.vpn_auth_type == "Certificate" ? 1 : 0
  cert_request_pem      = tls_cert_request.vpn_client[0].cert_request_pem
  ca_private_key_pem    = tls_private_key.vpn_root_ca[0].private_key_pem
  ca_cert_pem           = tls_self_signed_cert.vpn_root_ca[0].cert_pem
  validity_period_hours = 8760 # 1 year

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "client_auth",
  ]
}

# Extract public key in required format (base64 without headers)
locals {
  # Remove header, footer, and newlines from certificate
  vpn_cert_data = var.vpn_auth_type == "Certificate" ? trimspace(
    replace(
      replace(
        replace(
          tls_self_signed_cert.vpn_root_ca[0].cert_pem,
          "-----BEGIN CERTIFICATE-----", ""
        ),
        "-----END CERTIFICATE-----", ""
      ),
      "\n", ""
    )
  ) : ""
}

# VPN Gateway (this takes 30-45 minutes to create)
resource "azurerm_virtual_network_gateway" "vpn" {
  name                = "vng-hub-${local.resource_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  type     = "Vpn"
  vpn_type = "RouteBased"

  active_active = false
  bgp_enabled   = false
  sku           = var.vpn_gateway_sku

  ip_configuration {
    name                          = "vnetGatewayConfig"
    public_ip_address_id          = azurerm_public_ip.vpn_gateway.id
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.gateway.id
  }

  vpn_client_configuration {
    address_space        = var.vpn_client_address_pool
    vpn_client_protocols = var.vpn_auth_type == "AzureAD" ? ["OpenVPN"] : ["OpenVPN", "IkeV2"]

    # Azure AD Authentication (when vpn_auth_type == "AzureAD")
    aad_tenant   = var.vpn_auth_type == "AzureAD" ? "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/" : null
    aad_audience = var.vpn_auth_type == "AzureAD" ? "41b23e61-6c1e-4545-b367-cd054e0ed4b4" : null
    aad_issuer   = var.vpn_auth_type == "AzureAD" ? "https://sts.windows.net/${data.azurerm_client_config.current.tenant_id}/" : null

    # Certificate Authentication (when vpn_auth_type == "Certificate")
    dynamic "root_certificate" {
      for_each = var.vpn_auth_type == "Certificate" ? [1] : []
      content {
        name             = var.vpn_root_cert_name
        public_cert_data = local.vpn_cert_data
      }
    }
  }

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "p2s-vpn"
    }
  )
}
