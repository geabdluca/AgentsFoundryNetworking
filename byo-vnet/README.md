---
description: This set of templates demonstrates how to set up Azure AI Agent Service with virtual network isolation using your own VNet or the hub-spoke network infrastructure.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: network-secured-agent-byo-vnet
languages:
- hcl
---
# Updates
**01-27-2026** Added support for custom VNet (without hub-spoke dependency)

# Azure AI Agent Service: BYO VNet Deployment

This deployment creates AI Foundry resources with private networking. You can use it in two modes:

| Mode | Description |
|------|-------------|
| **Option 1: Hub-Spoke** | Use the hub-spoke-network deployment (recommended for new setups) |
| **Option 2: Custom VNet** | Bring your own VNet, subnets, and Private DNS Zones |

## Option 1: Using Hub-Spoke Network (Default)

This mode automatically reads network configuration from the hub-spoke-network deployment.

### Deployment Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STEP 1: Hub-Spoke Network                        │
│                      (../hub-spoke-network/code)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │   Hub VNet  │  │ Spoke VNet  │  │ VPN Gateway │  │ Private DNS     │ │
│  │  + DNS VM   │  │ + Subnets   │  │             │  │ Zones           │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘ │
│                              ↓                                           │
│                    terraform.tfstate (outputs)                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    terraform_remote_state reference
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                         STEP 2: BYO VNet (this deployment)               │
│                            (./code)                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │ AI Foundry  │  │  CosmosDB   │  │  AI Search  │  │ Storage Account │ │
│  │ + Project   │  │             │  │             │  │                 │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘ │
│                              ↓                                           │
│                    Private Endpoints → Spoke VNet                        │
│                    DNS Records → Hub-Spoke DNS Zones                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Prerequisites for Hub-Spoke Mode

1. **Deploy hub-spoke-network first**:
   ```bash
   cd ../hub-spoke-network/code
   terraform init
   terraform apply
   ```

2. **Active Azure subscription with appropriate permissions**

3. Terraform CLI version v1.11.4 or later

### Deploy with Hub-Spoke

```bash
cd byo-vnet/code
terraform init
terraform apply
```

---

## Option 2: Using Your Own VNet (Custom)

This mode allows you to bring your own existing VNet without the hub-spoke deployment.

### Prerequisites for Custom VNet Mode

You must have the following resources already deployed:

1. **Virtual Network** with two subnets:
   - **Private Endpoints Subnet**: For AI Foundry private endpoints
   - **Agents Subnet**: Delegated to `Microsoft.App/environments`

2. **Private DNS Zones** (linked to your VNet):
   - `privatelink.blob.core.windows.net`
   - `privatelink.documents.azure.com`
   - `privatelink.search.windows.net`
   - `privatelink.cognitiveservices.azure.com`
   - `privatelink.openai.azure.com`
   - `privatelink.services.ai.azure.com`

3. **DNS Resolution**: Your VNet must be able to resolve the Private DNS Zone FQDNs

### Deploy with Custom VNet

```bash
cd byo-vnet/code
cp example.tfvars terraform.tfvars
```

Edit `terraform.tfvars`:
```hcl
use_hub_spoke = false

subnet_id_private_endpoints = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/virtualNetworks/YOUR-VNET/subnets/YOUR-PE-SUBNET"
subnet_id_agents            = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/virtualNetworks/YOUR-VNET/subnets/YOUR-AGENTS-SUBNET"

private_dns_zone_ids = {
  blob_storage = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
  cosmos       = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.documents.azure.com"
  search       = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.search.windows.net"
  cognitive    = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com"
  openai       = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com"
  ai_services  = "/subscriptions/YOUR-SUB/resourceGroups/YOUR-RG/providers/Microsoft.Network/privateDnsZones/privatelink.services.ai.azure.com"
}

location            = "eastus"  # Must match your VNet region
resource_group_name = "rg-aifoundry-resources"
```

Then deploy:
```bash
$env:ARM_SUBSCRIPTION_ID = "your-subscription-id"
terraform init
terraform apply
```

---

## Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `use_hub_spoke` | Use hub-spoke-network deployment (true) or custom VNet (false) | `true` |
| `hub_spoke_state_path` | Path to hub-spoke terraform.tfstate (only if use_hub_spoke=true) | `../../hub-spoke-network/code/terraform.tfstate` |
| `subnet_id_private_endpoints` | Subnet ID for private endpoints (only if use_hub_spoke=false) | `null` |
| `subnet_id_agents` | Delegated subnet ID for agents (only if use_hub_spoke=false) | `null` |
| `private_dns_zone_ids` | Map of DNS zone IDs (only if use_hub_spoke=false) | `{}` |
| `resource_group_name` | Name of the resource group to create | `rg-aifoundry-resources` |
| `location` | Azure region (must match your VNet) | - |
| `environment` | Environment tag | `lab` |
| `tags` | Additional tags | `{}` |

---

## Architecture Overview

This deployment creates AI Foundry resources in a new resource group while using network infrastructure either from the hub-spoke deployment or your own custom VNet.

### Resources Created by This Deployment

- **Resource Group**: New resource group for AI Foundry resources
- **AI Foundry Account**: Central orchestration with network injection
- **AI Foundry Project**: Workspace with agent capabilities
- **CosmosDB Account**: Thread and agent state storage
- **Storage Account**: Agent data and blob storage
- **AI Search**: Vector embeddings and search capabilities
- **Private Endpoints**: For all services, deployed to Spoke VNet
- **Model Deployment**: GPT-4o (GlobalStandard)

### Network Requirements (from Hub-Spoke or Your Custom VNet)

- **Private Endpoints Subnet**: For AI Foundry private endpoints
- **Agents Subnet**: Delegated to `Microsoft.App/environments` for agent workloads
- **Private DNS Zones**: All required zones for private endpoint resolution
- **DNS Resolution**: VNet must resolve private DNS zone records

The deployment creates an isolated network environment:

- **Private Endpoints:**
  - AI Foundry
  - AI Search
  - CosmosDB
  - Storage

### Core Components

1. **AI Foundry Resource**
   - Central orchestration point
   - Manages service connections
   - Network-isolated capability hosts
2. **AI Project**
   - Workspace configuration
   - Service integration
   - Agent deployment
3. **Supporting Services for Standard Agent Deployment**
   - Azure AI Search
   - CosmosDB
   - Storage Account

---

## Security Features

### Authentication & Authorization

- **Managed Identity**
  - Zero-trust security model
  - No credential storage
  - Platform-managed rotation

- **Role Assignments**
  - **Azure AI Search**
    - Search Index Data Contributor (`8ebe5a00-799e-43f5-93ac-243d3dce84a7`)
    - Search Service Contributor (`7ca78c08-252a-4471-8644-bb5ff32d4ba0`)
  - **Azure Storage Account**
    - Storage Blob Data Owner (`b7e6dc6d-f1e8-4753-8033-0f276bb0955b`)
    - Storage Queue Data Contributor (`974c5e8b-45b9-4653-ba55-5f855dd0fb88`) (if Azure Function tool enabled)
    - Two containers will automatically be provisioned during the create capability host process:
      - Azure Blob Storage Container: `<workspaceId>-azureml-blobstore`
        - Storage Blob Data Contributor
      - Azure Blob Storage Container: `<workspaceId>-agents-blobstore`
        - Storage Blob Data Owner
  - **Key Vault**
    - Key Vault Contributor (`f25e0fa2-a7c8-4377-a976-54943a77a395`)
    - Key Vault Secrets Officer (`b86a8fe4-44ce-4948-aee5-eccb2c155cd7`)
  - **Cosmos DB for NoSQL**
    - Cosmos DB Operator (`230815da-be43-4aae-9cb4-875f7bd000aa`)
    - Cosmos DB Built-in Data Contributor
    - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-thread-message-store`
    - Cosmos DB for NoSQL container: `<${projectWorkspaceId}>-agent-entity-store`

### Network Security

- Public network access disabled
- Private endpoints for all services
- Service endpoints for Azure services
- Network ACLs with deny by default

---

## Clean Up / Destroy

### Destroy AI Foundry Only (Keep Hub-Spoke)

Use this when you want to tear down AI Foundry but keep the hub-spoke network for other deployments:

```powershell
cd byo-vnet/code

# Destroy the AI Foundry resources
terraform destroy

# IMPORTANT: Purge the soft-deleted Cognitive Services account
# AI Foundry uses soft-delete by default - purging is required before redeploying with same name
# or before deleting the VNet

# Purge all soft-deleted accounts in westus (one-liner)
az cognitiveservices account list-deleted --query "[?location=='westus']" -o json | ConvertFrom-Json | ForEach-Object { az cognitiveservices account purge --location $_.location --name $_.name --resource-group $_.resourceGroup }
```

### Destroy Everything (AI Foundry + Hub-Spoke)

```powershell
# 1. Destroy AI Foundry first
cd byo-vnet/code
terraform destroy

# 2. Purge all soft-deleted Cognitive Services in westus
az cognitiveservices account list-deleted --query "[?location=='westus']" -o json | ConvertFrom-Json | ForEach-Object { az cognitiveservices account purge --location $_.location --name $_.name --resource-group $_.resourceGroup }

# 3. Destroy hub-spoke network
cd ../../hub-spoke-network/code
terraform destroy
```

> ⚠️ **Why purge is required**: Azure Cognitive Services (AI Foundry) has soft-delete enabled by default with a retention period. The soft-deleted account holds references to the VNet subnets, which blocks VNet deletion. Purging removes the account immediately.

---

## Module Structure

```text
code/
├── data.tf                                         # Creates data objects for active subscription being deployed to and deployment security context
├── locals.tf                                       # Creates local variables for project GUID
├── main.tf                                         # Main deployment file        
├── outputs.tf                                      # Placeholder file for future outputs
├── providers.tf                                    # Terraform provider configuration 
├── example.tfvars                                  # Sample tfvars file
├── variables.tf                                    # Terraform variables
├── versions.tf                                     # Configures minimum Terraform version and versions for providers
```

## Maintenance

### Regular Tasks

1. Review role assignments
2. Monitor network security
3. Check service health
4. Update configurations as needed

### Troubleshooting

1. Verify private endpoint connectivity
2. Check DNS resolution
3. Validate role assignments
4. Review network security groups
5. **Browser blocks access to private resources**: Some Chromium-based browsers (Edge, Chrome) may block access to private network resources. Disable "Block insecure private network requests" in `edge://flags/` or `chrome://flags/` by searching for "Local Network Access Checks" and setting it to Disabled.

---

## References

- [Azure AI Foundry Networking Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?tabs=azure-portal&pivots=fdp-project)
- [Azure AI Foundry RBAC Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry?pivots=fdp-project)
- [Private Endpoint Documentation](https://learn.microsoft.com/en-us/azure/private-link/)
- [RBAC Documentation](https://learn.microsoft.com/en-us/azure/role-based-access-control/)
- [Network Security Best Practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices)
