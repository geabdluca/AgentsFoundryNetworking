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
  description = "Azure region for resources. Must support both Availability Zones (required by VPN Gateway AZ SKUs) AND AI Foundry Private Class A subnet injection. See: https://learn.microsoft.com/azure/ai-foundry/reference/region-support"
  type        = string
  default     = "eastus"

  validation {
    condition = contains([
      # Intersection: AZ-capable regions that also support AI Foundry Private Class A subnet
      "australiaeast",
      "brazilsouth",
      "eastus",
      "eastus2",
      "francecentral",
      "germanywestcentral",
      "italynorth",
      "japaneast",
      "southafricanorth",
      "southcentralus",
      "spaincentral",
      "swedencentral",
      "uaenorth",
      "uksouth",
      "westeurope",
      "westus3",
    ], var.location)
    error_message = "The region '${var.location}' is not supported. This deployment has two regional requirements:\n1. Availability Zone support (Azure VPN Gateway now requires AZ SKUs — non-AZ SKUs are retired)\n2. AI Foundry Private Class A subnet (networkInjections) GA support\nValid regions satisfying both: australiaeast, brazilsouth, eastus, eastus2, francecentral, germanywestcentral, italynorth, japaneast, southafricanorth, southcentralus, spaincentral, swedencentral, uaenorth, uksouth, westeurope, westus3.\nNote: westus and canadaeast support Foundry but not AZ — use westus3 or eastus instead."
  }
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

variable "hub_firewall_subnet_prefix" {
  description = "Address prefix for the Azure Firewall subnet in Hub VNet (must be at least /26)"
  type        = string
  default     = "10.0.2.0/26"
}

# Azure Firewall Configuration
variable "deploy_firewall" {
  description = "Deploy Azure Firewall in the Hub VNet with route table for agents subnet"
  type        = bool
  default     = false
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

variable "spoke_apim_subnet_prefix" {
  description = "Address prefix for APIM subnet in Spoke VNet (used when deploying Foundry + APIM option)"
  type        = string
  default     = "10.1.2.0/24"
}

# VPN Gateway Configuration
variable "vpn_gateway_sku" {
  description = "SKU for the VPN Gateway. Must be an AZ SKU (VpnGw1AZ-VpnGw5AZ) — non-AZ SKUs (VpnGw1-5) are no longer supported by Azure."
  type        = string
  default     = "VpnGw2AZ"
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
