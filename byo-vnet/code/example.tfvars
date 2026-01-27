# ============================================
# BYO VNet - AI Foundry Deployment
# ============================================

# ============================================
# Network Mode - Choose ONE option:
# ============================================

# OPTION 1: Use hub-spoke-network (default)
use_hub_spoke        = true
hub_spoke_state_path = "../../hub-spoke-network/code/terraform.tfstate"

# OPTION 2: Use your own VNet (uncomment and fill in)
# use_hub_spoke               = false
# subnet_id_private_endpoints = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/virtualNetworks/YOUR-VNET/subnets/YOUR-PE-SUBNET"
# subnet_id_agents            = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/virtualNetworks/YOUR-VNET/subnets/YOUR-AGENTS-SUBNET"
# private_dns_zone_ids = {
#   blob_storage = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
#   cosmos       = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.documents.azure.com"
#   search       = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.search.windows.net"
#   cognitive    = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com"
#   openai       = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com"
#   ai_services  = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.services.ai.azure.com"
# }

# ============================================
# Resource Configuration
# ============================================

# Resource group name for AI Foundry resources (will be created)
resource_group_name = "rg-aifoundry-resources"

# Azure region - MUST match your VNet region
location = "eastus"

# Environment tag
environment = "lab"

# Optional tags
tags = {
  project = "ai-foundry"
  owner   = "your-name"
}
