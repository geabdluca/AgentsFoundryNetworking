# ============================================
# Resource Group Outputs
# ============================================

output "resource_group_name" {
  description = "The name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "The location of the resource group"
  value       = azurerm_resource_group.main.location
}

output "resource_group_id" {
  description = "The ID of the resource group"
  value       = azurerm_resource_group.main.id
}

# ============================================
# Hub VNet Outputs
# ============================================

output "hub_vnet_id" {
  description = "The ID of the Hub VNet"
  value       = azurerm_virtual_network.hub.id
}

output "hub_vnet_name" {
  description = "The name of the Hub VNet"
  value       = azurerm_virtual_network.hub.name
}

output "hub_vnet_address_space" {
  description = "The address space of the Hub VNet"
  value       = azurerm_virtual_network.hub.address_space
}

output "hub_dns_subnet_id" {
  description = "The ID of the DNS subnet in Hub VNet"
  value       = azurerm_subnet.dns.id
}

# ============================================
# Spoke VNet Outputs
# ============================================

output "spoke_vnet_id" {
  description = "The ID of the Foundry Spoke VNet (use this for Managed VNet configuration)"
  value       = azurerm_virtual_network.spoke.id
}

output "spoke_vnet_name" {
  description = "The name of the Foundry Spoke VNet"
  value       = azurerm_virtual_network.spoke.name
}

output "spoke_vnet_address_space" {
  description = "The address space of the Foundry Spoke VNet"
  value       = azurerm_virtual_network.spoke.address_space
}

output "spoke_private_endpoints_subnet_id" {
  description = "The ID of the private endpoints subnet in Spoke VNet"
  value       = azurerm_subnet.spoke_private_endpoints.id
}

output "spoke_delegated_subnet_id" {
  description = "The ID of the delegated subnet in Spoke VNet (for Managed VNet)"
  value       = azurerm_subnet.spoke_delegated.id
}

# ============================================
# VPN Gateway Outputs
# ============================================

output "vpn_gateway_id" {
  description = "The ID of the VPN Gateway"
  value       = azurerm_virtual_network_gateway.vpn.id
}

output "vpn_gateway_public_ip" {
  description = "The public IP address of the VPN Gateway"
  value       = azurerm_public_ip.vpn_gateway.ip_address
}

output "vpn_client_address_pool" {
  description = "The address pool for VPN clients"
  value       = var.vpn_client_address_pool
}

output "vpn_authentication_type" {
  description = "The VPN authentication type"
  value       = var.vpn_auth_type
}

# Certificate Authentication Outputs
output "vpn_root_certificate_name" {
  description = "The name of the VPN root certificate"
  value       = var.vpn_auth_type == "Certificate" ? var.vpn_root_cert_name : null
}

output "vpn_root_certificate_pem" {
  description = "The root certificate in PEM format (for reference only)"
  value       = var.vpn_auth_type == "Certificate" ? tls_self_signed_cert.vpn_root_ca[0].cert_pem : null
  sensitive   = true
}

output "vpn_client_certificate_pem" {
  description = "The client certificate in PEM format"
  value       = var.vpn_auth_type == "Certificate" ? tls_locally_signed_cert.vpn_client[0].cert_pem : null
  sensitive   = true
}

output "vpn_client_private_key_pem" {
  description = "The client certificate private key in PEM format"
  value       = var.vpn_auth_type == "Certificate" ? tls_private_key.vpn_client[0].private_key_pem : null
  sensitive   = true
}

# Azure AD Authentication Outputs
output "vpn_aad_tenant" {
  description = "The Azure AD tenant ID used for VPN authentication"
  value       = var.vpn_auth_type == "AzureAD" ? data.azurerm_client_config.current.tenant_id : null
}

output "vpn_aad_audience" {
  description = "The Azure AD audience/client ID for VPN"
  value       = var.vpn_auth_type == "AzureAD" ? "41b23e61-6c1e-4545-b367-cd054e0ed4b4" : null
}

# ============================================
# DNS VM Outputs
# ============================================

output "dns_vm_name" {
  description = "The name of the DNS VM"
  value       = azurerm_windows_virtual_machine.dns.name
}

output "dns_vm_private_ip" {
  description = "The private IP address of the DNS VM"
  value       = azurerm_network_interface.dns_vm.private_ip_address
}

output "dns_vm_admin_username" {
  description = "The admin username for the DNS VM"
  value       = var.dns_vm_admin_username
}

output "dns_vm_admin_password" {
  description = "The admin password for the DNS VM"
  value       = random_password.dns_vm_password.result
  sensitive   = true
}

output "dns_vm_id" {
  description = "The ID of the DNS VM"
  value       = azurerm_windows_virtual_machine.dns.id
}

# ============================================
# Private DNS Zones Outputs
# ============================================

output "private_dns_zone_ids" {
  description = "Map of Private DNS Zone IDs (use these for Managed VNet configuration)"
  value = var.create_private_dns_zones ? {
    for key, zone in azurerm_private_dns_zone.zones : key => zone.id
  } : {}
}

output "private_dns_zone_names" {
  description = "Map of Private DNS Zone names"
  value = var.create_private_dns_zones ? {
    for key, zone in azurerm_private_dns_zone.zones : key => zone.name
  } : {}
}

# ============================================
# Instructions Output
# ============================================

output "next_steps" {
  description = "Next steps for using this hub-spoke network"
  value       = <<-EOT
    ===================================
    Hub-Spoke Network Deployment Complete!
    ===================================
    
    VPN Authentication: ${var.vpn_auth_type}
    
    ${var.vpn_auth_type == "Certificate" ? "1. Install VPN Client Certificate (run after deployment):\n   terraform output -raw vpn_client_certificate_pem > cert.pem\n   terraform output -raw vpn_client_private_key_pem > key.pem\n   .\\install-vpn-cert.ps1 -CertificatePem (Get-Content cert.pem -Raw) -PrivateKeyPem (Get-Content key.pem -Raw)\n   Remove-Item cert.pem, key.pem\n\n2. Download VPN Client:\n   - Gateway: ${azurerm_virtual_network_gateway.vpn.name}\n   - Public IP: ${azurerm_public_ip.vpn_gateway.ip_address}\n   - Azure Portal > VPN Gateway > Point-to-site > Download VPN client\n   - For Windows: Run OpenVPN\\VpnClientSetup.exe\n   - Certificate will be used automatically\n" : "IMPORTANT: Admin Consent Required!\nBefore connecting, an admin must grant consent:\nhttps://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/adminconsent?client_id=41b23e61-6c1e-4545-b367-cd054e0ed4b4\n\n1. VPN Setup:\n   - Download Azure VPN Client from Microsoft Store\n   - Gateway: ${azurerm_virtual_network_gateway.vpn.name}\n   - Public IP: ${azurerm_public_ip.vpn_gateway.ip_address}\n   - Azure Portal > VPN Gateway > Point-to-site > Download VPN client\n   - Import azurevpnconfig.xml and sign in with Azure AD\n"}
    ${var.vpn_auth_type == "Certificate" ? "3" : "2"}. DNS VM Configuration:
       - VM: ${azurerm_windows_virtual_machine.dns.name}
       - IP: ${azurerm_windows_virtual_machine.dns.private_ip_address}
       - Username: ${azurerm_windows_virtual_machine.dns.admin_username}
       - Password: terraform output -raw dns_vm_admin_password
    
    ${var.vpn_auth_type == "Certificate" ? "4" : "3"}. Configure VNet DNS:
       - Update Hub and Spoke VNets to use DNS: ${azurerm_windows_virtual_machine.dns.private_ip_address}
    
    ${var.vpn_auth_type == "Certificate" ? "5" : "4"}. Deploy AI Foundry:
       - Use ../18-managed-virtual-network-preview/ template
       - existing_vnet_id = "${azurerm_virtual_network.spoke.id}"
       - existing_subnet_id = "${azurerm_subnet.spoke_delegated.id}"
    
    For detailed instructions, see README.md
  EOT
}
