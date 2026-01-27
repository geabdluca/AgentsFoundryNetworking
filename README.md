# Azure AI Foundry with Private Network

Deploy Azure AI Foundry with full network isolation using a hub-spoke network topology and BYO (Bring Your Own) VNet approach.

## Documentation

| Module | Description |
|--------|-------------|
| **[Hub-Spoke Network](./hub-spoke-network/README.md)** | VPN Gateway, DNS Server, Private DNS Zones, VNet Peering |
| **[BYO VNet AI Foundry](./byo-vnet/README.md)** | AI Foundry, Cosmos DB, AI Search, Storage with Private Endpoints |

---

## Quick Start

### Step 1: Deploy Hub-Spoke Network (~30-60 min)

```powershell
cd hub-spoke-network/code

# Configure
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your subscription_id and location

# Deploy
terraform init
terraform apply
```

### Step 2: Configure DNS & VPN

```powershell
# Go back to hub-spoke-network root (scripts are there)
cd ..

# Install DNS Server on the DNS VM
.\install-dns-server.ps1

# Install VPN certificates (run as Administrator)
Start-Process powershell -Verb RunAs -ArgumentList "-NoExit", "-Command", "cd '$PWD'; .\install-vpn-certs.ps1"

# Download and install VPN client
cd code
$rgName = terraform output -raw resource_group_name
$vpnGwId = terraform output -raw vpn_gateway_id
$vpnGwName = $vpnGwId.Split('/')[-1]
$url = az network vnet-gateway vpn-client generate --resource-group $rgName --name $vpnGwName --processor-architecture Amd64 --output tsv
Invoke-WebRequest -Uri $url -OutFile "../VpnClient.zip"
Expand-Archive -Path "../VpnClient.zip" -DestinationPath "../VpnClient" -Force
..\VpnClient\WindowsAmd64\VpnClientSetupAmd64.exe
```

### Step 3: Deploy AI Foundry (~20-30 min)

```powershell
cd ../byo-vnet/code

# Configure (location auto-detected from hub-spoke)
cp example.tfvars terraform.tfvars
# Edit terraform.tfvars - set location to match hub-spoke

# Deploy
$env:ARM_SUBSCRIPTION_ID = "your-subscription-id"
terraform init
terraform apply
```

### Step 4: Connect & Test

1. Connect to VPN
2. Test DNS resolution:
   ```powershell
   nslookup <ai foundry name>.services.ai.azure.com
   ```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Hub VNet (10.0.0.0/16)                   │
│   ┌──────────────┐              ┌─────────────────┐        │
│   │ VPN Gateway  │              │    DNS VM       │        │
│   │   (P2S)      │              │   10.0.1.4      │        │
│   └──────────────┘              └─────────────────┘        │
└────────────────────────────┬────────────────────────────────┘
                             │ VNet Peering
┌────────────────────────────▼────────────────────────────────┐
│                  Spoke VNet (10.1.0.0/16)                   │
│   ┌──────────────────┐         ┌──────────────────┐        │
│   │ Private Endpoints│         │ Agents Subnet    │        │
│   │ Subnet           │         │ (Delegated)      │        │
│   └──────────────────┘         └──────────────────┘        │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│              AI Foundry Resources (New RG)                  │
│                                                             │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐  │
│  │ AI Foundry│ │ Cosmos DB │ │ AI Search │ │  Storage  │  │
│  │ + Project │ │           │ │           │ │  Account  │  │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Folder Structure

```
AgentsFoundryNetworking/
├── hub-spoke-network/          # Step 1: Network infrastructure
│   ├── README.md               # Detailed network setup guide
│   ├── install-dns-server.ps1  # DNS configuration script
│   ├── install-vpn-certs.ps1   # VPN certificate script
│   └── code/                   # Terraform code
│       ├── terraform.tfvars    # Your configuration
│       └── *.tf
│
└── byo-vnet/                   # Step 2: AI Foundry resources
    ├── README.md               # AI Foundry deployment guide
    ├── deploy-byo-vnet.ps1     # Automated deployment script
    └── code/
        ├── terraform.tfvars
        └── *.tf
```

## What Gets Deployed

### Hub-Spoke Network
| Resource | Purpose |
|----------|---------|
| Hub VNet | Central connectivity |
| Spoke VNet | AI Foundry resources |
| VPN Gateway | Remote access |
| DNS VM | Private DNS resolution |
| Private DNS Zones | 12 zones for Azure services |
| VNet Peering | Hub-spoke connectivity |

### AI Foundry (BYO VNet)
| Resource | Purpose |
|----------|---------|
| Resource Group | New RG for AI resources |
| AI Foundry Account | AI services hub |
| AI Foundry Project | Workspace for agents |
| Cosmos DB | Thread/agent state storage |
| AI Search | Vector embeddings |
| Storage Account | Agent data |
| Private Endpoints | Secure connectivity |
| GPT-4o Deployment | AI model |

## Estimated Costs

| Resource | Monthly Cost |
|----------|-------------|
| VPN Gateway (VpnGw2) | ~$260 |
| DNS VM (D2s_v3) | ~$70 |
| AI Search (Standard) | ~$250 |
| Cosmos DB | ~$25 |
| Storage Account | ~$5 |
| **Total** | **~$610/month** |

## Troubleshooting

See the troubleshooting sections in each module's README:
- [Hub-Spoke Troubleshooting](./hub-spoke-network/README.md#troubleshooting)
- [BYO VNet Troubleshooting](./byo-vnet/README.md#troubleshooting)

## Clean Up

### Destroy AI Foundry Only (Keep Hub-Spoke for Reuse)
```powershell
cd byo-vnet/code
terraform destroy

# Purge soft-deleted Cognitive Services (required before redeploying or deleting VNet)
az cognitiveservices account list-deleted --query "[?location=='westus']" -o table
az cognitiveservices account purge --location westus --name <account-name> --resource-group <rg-name>
```

### Destroy Everything
```powershell
# 1. Destroy AI Foundry
cd byo-vnet/code
terraform destroy

# 2. Purge soft-deleted Cognitive Services
az cognitiveservices account list-deleted --query "[?location=='westus']" -o table
az cognitiveservices account purge --location westus --name <account-name> --resource-group <rg-name>

# 3. Destroy hub-spoke network
cd ../../hub-spoke-network/code
terraform destroy
```

> ⚠️ **Important**: AI Foundry uses soft-delete by default. Purging is required before the VNet can be deleted or before redeploying with the same name.

> ⚠️ VPN Gateway deletion takes 15-20 minutes.
