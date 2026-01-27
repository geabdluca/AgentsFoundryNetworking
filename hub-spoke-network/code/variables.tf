variable "subscription_id" {
  description = "The Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "The name prefix of the resource group"
  type        = string
  default     = "rg-aifoundry-hubspoke"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Environment name (e.g., dev, test, prod)"
  type        = string
  default     = "lab"
}

variable "tags" {
  description = "A map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# VPN Authentication Configuration
variable "vpn_auth_type" {
  description = "VPN authentication type: 'Certificate' or 'AzureAD'"
  type        = string
  default     = "Certificate"
  validation {
    condition     = contains(["Certificate", "AzureAD"], var.vpn_auth_type)
    error_message = "vpn_auth_type must be either 'Certificate' or 'AzureAD'."
  }
}

variable "vpn_root_cert_name" {
  description = "Name for the VPN root certificate"
  type        = string
  default     = "P2SRootCert"
}

variable "vpn_client_cert_name" {
  description = "Name for the VPN client certificate"
  type        = string
  default     = "P2SClientCert"
}

# Hub VNet Configuration
variable "hub_vnet_address_space" {
  description = "Address space for the Hub VNet"
  type        = string
  default     = "10.0.0.0/16"
}

variable "hub_gateway_subnet_prefix" {
  description = "Address prefix for the Gateway subnet in Hub VNet"
  type        = string
  default     = "10.0.0.0/27"
}

variable "hub_dns_subnet_prefix" {
  description = "Address prefix for the DNS subnet in Hub VNet"
  type        = string
  default     = "10.0.1.0/24"
}

# Spoke VNet Configuration
variable "spoke_vnet_address_space" {
  description = "Address space for the Foundry Spoke VNet"
  type        = string
  default     = "10.1.0.0/16"
}

variable "spoke_private_endpoints_subnet_prefix" {
  description = "Address prefix for private endpoints subnet in Spoke VNet"
  type        = string
  default     = "10.1.0.0/24"
}

variable "spoke_delegated_subnet_prefix" {
  description = "Address prefix for delegated subnet (for managed VNet) in Spoke VNet"
  type        = string
  default     = "10.1.1.0/24"
}

# VPN Gateway Configuration
variable "vpn_gateway_sku" {
  description = "SKU for the VPN Gateway"
  type        = string
  default     = "VpnGw2"
}

variable "vpn_client_address_pool" {
  description = "Address pool for VPN clients (Point-to-Site)"
  type        = list(string)
  default     = ["172.16.0.0/24"]
}

variable "vpn_root_certificate_name" {
  description = "Name for the VPN root certificate (optional - if not provided, self-signed cert will be generated)"
  type        = string
  default     = "P2SRootCert"
}

variable "vpn_root_certificate_data" {
  description = "Public certificate data for VPN root certificate (Base64 encoded, without BEGIN/END headers). Leave empty to generate self-signed certificate."
  type        = string
  default     = ""
  sensitive   = true
}

# DNS VM Configuration
variable "dns_vm_name" {
  description = "Name for the DNS virtual machine"
  type        = string
  default     = "vm-dns"
}

variable "dns_vm_size" {
  description = "Size for the DNS virtual machine"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "dns_vm_admin_username" {
  description = "Admin username for the DNS VM"
  type        = string
  default     = "azureuser"
}

variable "dns_vm_os_disk_size_gb" {
  description = "OS disk size in GB for the DNS VM"
  type        = number
  default     = 128
}

# Private DNS Zones to create
variable "create_private_dns_zones" {
  description = "Create Azure Private DNS Zones for AI services"
  type        = bool
  default     = true
}

variable "private_dns_zones" {
  description = "Map of Private DNS zones to create"
  type        = map(string)
  default = {
    cosmos              = "privatelink.documents.azure.com"
    search              = "privatelink.search.windows.net"
    cognitive           = "privatelink.cognitiveservices.azure.com"
    openai              = "privatelink.openai.azure.com"
    ai_services         = "privatelink.services.ai.azure.com"
    blob_storage        = "privatelink.blob.core.windows.net"
    file_storage        = "privatelink.file.core.windows.net"
    table_storage       = "privatelink.table.core.windows.net"
    queue_storage       = "privatelink.queue.core.windows.net"
    keyvault            = "privatelink.vaultcore.azure.net"
    aifoundry_api       = "privatelink.api.azureml.ms"
    aifoundry_notebooks = "privatelink.notebooks.azure.net"
  }
}
