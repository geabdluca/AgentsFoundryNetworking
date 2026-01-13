# Hub-Spoke Network Infrastructure for Azure AI Foundry

This Terraform module creates a complete hub-spoke network architecture to support Azure AI Foundry deployments with managed virtual networks. This infrastructure is designed for organizations that need to establish network connectivity before deploying AI Foundry resources.

## Quick Start

Get your infrastructure deployed in under 60 minutes:

### 1. Prerequisites

**Required Tools:** [Detailed installation instructions](#prerequisites)
- Terraform >= 1.0
- Azure CLI >= 2.40
- OpenSSL >= 3.0 (for certificate installation)
- PowerShell 7+ (recommended)

```powershell
# Quick install (Windows)
winget install Hashicorp.Terraform
winget install Microsoft.AzureCLI
winget install FireDaemon.OpenSSL

# Login to Azure
az login
az account set --subscription "YOUR-SUBSCRIPTION-ID"
```

### 2. Configure
```powershell
# Clone or navigate to the hub-spoke-network directory
cd hub-spoke-network

# Create terraform.tfvars
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values (location, naming prefix, etc.)
```

### 3. Deploy (45-60 minutes)
```powershell
# Initialize and deploy
terraform init
terraform plan
terraform apply
```

### 4. Configure DNS
```powershell
# Install DNS Server on the DNS VM
.\install-dns-server.ps1

# This configures:
# - DNS Server role installation
# - Azure DNS forwarder (168.63.129.16)
# - 12 conditional forwarders for AI services
```

### 5. Configure VPN Access
```powershell
# Run as Administrator - installs certificates to CurrentUser stores
.\install-vpn-certs.ps1

# Download VPN client automatically
$rgName = terraform output -raw resource_group_name; $vpnGwId = terraform output -raw vpn_gateway_id; $vpnGwName = $vpnGwId.Split('/')[-1]; $url = az network vnet-gateway vpn-client generate --resource-group $rgName --name $vpnGwName --processor-architecture Amd64 --output tsv; Invoke-WebRequest -Uri $url -OutFile "VpnClient.zip"; Expand-Archive -Path "VpnClient.zip" -DestinationPath "VpnClient" -Force; Write-Host "VPN client downloaded to VpnClient folder" -ForegroundColor Green

# Install VPN client
.\VpnClient\WindowsAmd64\VpnClientSetupAmd64.exe

# Connect to VPN (certificates will be used automatically)
```

### 6. Test Connectivity
```powershell
# After VPN is connected, test DNS resolution
nslookup services.ai.azure.com 10.0.1.4
nslookup api.azureml.ms 10.0.1.4
nslookup privatelink.services.ai.azure.com 10.0.1.4
```

### 7. Ready!
Your infrastructure is ready for Azure AI Foundry deployment with:
- VPN connectivity established
- DNS resolution configured
- Private DNS zones linked
- Network secured with NSGs

---

## Table of Contents

- [Configuration Variables](#configuration-variables)
- [Overview](#overview)
- [Architecture](#architecture)
- [When to Use This Module](#when-to-use-this-module)
- [Components](#components)
- [Prerequisites](#prerequisites)
- [Cleanup](#cleanup)
- [Troubleshooting](#troubleshooting)

## Overview

This module provisions:
- **Hub VNet** with Point-to-Site VPN Gateway for secure remote access
- **Foundry Spoke VNet** for AI resources with delegated subnet support
- **Windows Server DNS VM** configured with conditional forwarders
- **Azure Private DNS Zones** for all AI services
- **VNet Peering** with Gateway Transit enabled

## Architecture

The hub-spoke topology provides:
- Centralized network connectivity through the Hub
- Isolated AI workloads in the Spoke
- Secure VPN access for administrators
- Custom DNS resolution for hybrid scenarios

```
┌─────────────────────────────────────────────────────┐
│                    Hub VNet                         │
│                  (10.0.0.0/16)                      │
│                                                     │
│  ┌──────────────┐         ┌─────────────────┐     │
│  │ VPN Gateway  │         │   DNS VM        │     │
│  │   (P2S)      │         │  (Windows 2022) │     │
│  │  VpnGw2 SKU  │         │  Conditional    │     │
│  └──────────────┘         │  Forwarders     │     │
│                           └─────────────────┘     │
└─────────────┬───────────────────────────────────────┘
              │ VNet Peering
              │ (Gateway Transit Enabled)
              │
┌─────────────▼───────────────────────────────────────┐
│              Foundry Spoke VNet                     │
│                (10.1.0.0/16)                        │
│                                                     │
│  ┌──────────────────────┐  ┌──────────────────┐   │
│  │ Private Endpoints    │  │ Delegated Subnet │   │
│  │    Subnet            │  │  (for Managed    │   │
│  │  (AI Services PEs)   │  │   VNet)          │   │
│  └──────────────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────┘

        ┌───────────────────────────────┐
        │  Azure Private DNS Zones      │
        │  - Cognitive Services         │
        │  - OpenAI                     │
        │  - Storage (Blob/File/etc)    │
        │  - Cosmos DB                  │
        │  - AI Search                  │
        │  - Key Vault                  │
        │  - AI Foundry                 │
        └───────────────────────────────┘
```

## Components

### 1. Hub Virtual Network (10.0.0.0/16)

| Subnet | Address Space | Purpose |
|--------|--------------|---------|
| GatewaySubnet | 10.0.0.0/27 | VPN Gateway |
| snet-dns | 10.0.1.0/24 | DNS Virtual Machine |

### 2. Spoke Virtual Network (10.1.0.0/16)

| Subnet | Address Space | Purpose |
|--------|--------------|---------|
| snet-privateendpoints | 10.1.0.0/24 | Private endpoints for AI services |
| snet-delegated | 10.1.1.0/24 | Delegated for AI Foundry managed VNet |

### 3. VPN Gateway
- **SKU**: VpnGw2
- **Type**: Point-to-Site (P2S)
- **Protocols**: OpenVPN, IkeV2
- **Client Address Pool**: 172.16.0.0/24
- **Certificate**: Self-signed root CA (auto-generated)

### 4. DNS Virtual Machine
- **OS**: Windows Server 2022 Datacenter
- **Size**: Standard_D2s_v3 (2 vCPU, 8GB RAM)
- **Authentication**: Password-based (auto-generated)
- **Configuration**: DNS Server role (installed via post-deployment script)
- **Private IP**: 10.0.1.4 (static)

⚠️ **Important**: The DNS Server role is installed via a separate post-deployment script (`install-dns-server.ps1`), NOT during Terraform deployment. This ensures reliable installation and proper error handling.

After running the DNS installation script, the DNS VM will have:
- DNS Server role installed
- Forwarder to Azure recursive resolver (168.63.129.16)
- Conditional forwarders for 12 public Azure DNS zones (documents.azure.com, search.windows.net, etc.)

### 5. Private DNS Zones

The following Azure Private DNS Zones are created and linked to both VNets:

| Service | Private DNS Zone |
|---------|-----------------|
| Cognitive Services | privatelink.cognitiveservices.azure.com |
| OpenAI | privatelink.openai.azure.com |
| Blob Storage | privatelink.blob.core.windows.net |
| File Storage | privatelink.file.core.windows.net |
| Table Storage | privatelink.table.core.windows.net |
| Queue Storage | privatelink.queue.core.windows.net |
| Key Vault | privatelink.vaultcore.azure.net |
| AI Foundry API | privatelink.api.azureml.ms |
| AML Notebooks | privatelink.notebooks.azure.net |
| Cosmos DB | privatelink.documents.azure.com |
| AI Search | privatelink.search.windows.net |

## Prerequisites

### Azure Subscription Requirements
- **Active Azure subscription** with Owner or Contributor permissions
- **Resource Providers registered**:
  ```bash
  az provider register --namespace Microsoft.Network
  az provider register --namespace Microsoft.Compute
  ```

### Required Tools Installation

#### 1. Install Terraform

**Windows (using Chocolatey):**
```powershell
# Install Chocolatey if not already installed
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install Terraform
choco install terraform -y
```

**Windows (using winget):**
```powershell
winget install --id HashiCorp.Terraform
```

**Manual Installation (Windows/Mac/Linux):**
1. Download from [Terraform Downloads](https://www.terraform.io/downloads.html)
2. Extract the executable
3. Add to your system PATH

**Verify Installation:**
```bash
terraform version
# Should show: Terraform v1.0 or higher
```

#### 2. Install Azure CLI

**Windows:**
```powershell
# Using winget (recommended)
winget install -e --id Microsoft.AzureCLI

# Or using MSI installer
# Download from: https://aka.ms/installazurecliwindows
```

**Mac:**
```bash
brew update && brew install azure-cli
```

**Linux (Ubuntu/Debian):**
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

**Verify Installation:**
```bash
az version
# Should show version 2.40 or higher
```

**Login to Azure:**
```bash
az login
az account set --subscription "YOUR-SUBSCRIPTION-ID"
```

#### 3. Install OpenSSL (Required for Certificate Installation)

**Windows (using winget - recommended):**
```powershell
# Install OpenSSL
winget install FireDaemon.OpenSSL

# Verify installation
openssl version
# Should show: OpenSSL 3.x or higher
```

**Windows (using Chocolatey):**
```powershell
choco install openssl -y
```

**Mac:**
```bash
# OpenSSL is pre-installed on macOS
# Verify version
openssl version
```

**Linux:**
```bash
# Usually pre-installed, if not:
sudo apt-get update
sudo apt-get install openssl
```

#### 4. Install PowerShell 7+ (Windows/Mac/Linux)

**Windows (using winget):**
```powershell
winget install --id Microsoft.Powershell
```

**Mac:**
```bash
brew install --cask powershell
```

**Linux:**
```bash
# Ubuntu/Debian
wget https://aka.ms/install-powershell.sh
sudo bash install-powershell.sh
```

**Verify Installation:**
```powershell
$PSVersionTable.PSVersion
# Should show version 7.0 or higher
```

### Tool Verification Checklist

Run these commands to verify all tools are properly installed:

```powershell
# Verify Terraform
terraform version

# Verify Azure CLI
az version

# Verify OpenSSL
openssl version

# Verify PowerShell version
$PSVersionTable.PSVersion

# Verify Azure login
az account show
```

✅ All commands should complete successfully before proceeding with deployment.

### Estimated Deployment Time
- **Total**: ~45-60 minutes
  - VPN Gateway: 30-45 minutes
  - VNet, Subnets, Peering: 5-10 minutes
  - DNS VM: 5-10 minutes
  - Private DNS Zones: 2-5 minutes

### Estimated Monthly Cost
Approximate costs (East US region):
- VPN Gateway (VpnGw2): ~$260/month
- DNS VM (Standard_D2s_v3): ~$70/month
- VNets, Peering, DNS Zones: <$10/month
- **Total**: ~$340/month

## Configuration Variables

Customize your deployment by editing `terraform.tfvars`. Copy from the example file:

```powershell
cp terraform.tfvars.example terraform.tfvars
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|----------|
| `subscription_id` | Your Azure Subscription ID | `00000000-0000-0000-0000-000000000000` |

### Optional Variables

All optional variables have sensible defaults. Customize as needed:

#### Resource Naming and Location

| Variable | Default | Description |
|----------|---------|-------------|
| `resource_group_name` | `rg-aifoundry-hubspoke` | Name for the resource group |
| `location` | `eastus` | Azure region for all resources |
| `environment` | `lab` | Environment identifier (dev/test/prod) |
| `tags` | See example | Resource tags for organization and billing |

#### Network Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `hub_vnet_address_space` | `10.0.0.0/16` | Hub VNet CIDR block |
| `hub_gateway_subnet_prefix` | `10.0.0.0/27` | Gateway subnet (min /27 required) |
| `hub_dns_subnet_prefix` | `10.0.1.0/24` | DNS VM subnet |
| `spoke_vnet_address_space` | `10.1.0.0/16` | Spoke VNet CIDR block |
| `spoke_private_endpoints_subnet_prefix` | `10.1.0.0/24` | Private endpoints subnet |
| `spoke_delegated_subnet_prefix` | `10.1.1.0/24` | Delegated subnet for managed services |

#### VPN Gateway Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `vpn_gateway_sku` | `VpnGw2` | Gateway SKU (VpnGw1/VpnGw2/VpnGw3) |
| `vpn_client_address_pool` | `["172.16.0.0/24"]` | Address pool for VPN clients |
| `vpn_root_certificate_name` | `P2SRootCert` | Root certificate name |
| `vpn_root_certificate_data` | (auto-generated) | Base64 certificate data (leave empty for auto-generation) |

#### DNS VM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `dns_vm_name` | `vm-dns` | DNS virtual machine name |
| `dns_vm_size` | `Standard_D2s_v3` | VM SKU size |
| `dns_vm_admin_username` | `azureuser` | Admin username |
| `dns_vm_os_disk_size_gb` | `128` | OS disk size in GB |

#### Private DNS Zones

| Variable | Default | Description |
|----------|---------|-------------|
| `create_private_dns_zones` | `true` | Create 12 AI service Private DNS zones |

**Note:** DNS zones are automatically created for Azure AI services including OpenAI, Cognitive Services, Storage, Key Vault, Container Registry, and Machine Learning.

### Example Configuration

```hcl
# terraform.tfvars
subscription_id = "your-subscription-id-here"

# Customize naming and location
resource_group_name = "rg-myproject-network"
location            = "westus"
environment         = "dev"

# Adjust network addressing if you have conflicts
hub_vnet_address_space  = "10.10.0.0/16"
spoke_vnet_address_space = "10.11.0.0/16"

# Use a smaller/cheaper VPN gateway for dev
vpn_gateway_sku = "VpnGw1"

# Custom tags
tags = {
  Project     = "My AI Project"
  CostCenter  = "Engineering"
  Owner       = "your.email@company.com"
}
```

## Cleanup

To remove all resources:

### Step 1: Destroy Hub-Spoke Resources
```bash
cd hub-spoke-network
terraform destroy
```

⚠️ **Note**: VPN Gateway deletion takes 15-20 minutes.

### Step 2: Verify Deletion
Check that all resources are removed:
```bash
az group list --query "[?starts_with(name,'rg-aifoundry-hubspoke')].name" -o table
```

### Cost Optimization
If you want to keep the infrastructure but reduce costs temporarily:
- **Stop the DNS VM**: Saves ~$70/month
- **Keep VPN Gateway**: Required for connectivity, cannot be stopped

## Troubleshooting

### Certificate Installation Issues

#### Error: "A certificate could not be found" (Error 798)
**Symptom**: VPN connection fails with certificate not found error

**Root Cause**: ⚠️ The Windows VPN client requires certificates in the **CurrentUser** certificate stores, NOT LocalMachine stores. This is a common issue when using the standard installation approach.

**Solution - Use fix-vpn-certificates.ps1**:

This script properly installs certificates to the correct stores:

```powershell
# Run the certificate installation script (handles everything automatically)
cd hub-spoke-network
.\install-vpn-certs.ps1

# The script will:
# 1. Export certificates from Terraform outputs
# 2. Format PEM files correctly (required for OpenSSL)
# 3. Create PFX file with client cert and private key
# 4. Install Root CA to CurrentUser\Root
# 5. Install Client cert with private key to CurrentUser\My
# 6. Clean up temporary files
# 7. Verify installation
```

**Manual Verification**:
```powershell
# Check client certificate (should have private key)
Get-ChildItem Cert:\CurrentUser\My | Where-Object {$_.Subject -like "*vpn-client*"}

# Check root CA
Get-ChildItem Cert:\CurrentUser\Root | Where-Object {$_.Subject -like "*vpn-root-ca*"}

# Verify the client cert has a private key
Get-ChildItem Cert:\CurrentUser\My | Where-Object {$_.Subject -like "*vpn-client*"} | Select-Object Subject, Thumbprint, HasPrivateKey

# Should show: HasPrivateKey : True
```

**Why CurrentUser stores?**:
- Windows VPN client runs in user context, not system context
- Certificates in LocalMachine\My are not accessible to the VPN client
- The VPN client specifically looks for certificates in CurrentUser stores
- Both the client certificate AND root CA must be in CurrentUser stores

**If still experiencing Error 798**:
1. **Verify OpenSSL is installed**:
   ```powershell
   openssl version
   # If not found: winget install FireDaemon.OpenSSL
   ```

2. **Check certificate thumbprints match**:
   ```powershell
   # Get expected thumbprints from Terraform
   terraform output vpn_client_certificate_thumbprint
   terraform output vpn_root_certificate_thumbprint
   
   # Compare with installed certificates
   Get-ChildItem Cert:\CurrentUser\My | Select-Object Subject, Thumbprint
   Get-ChildItem Cert:\CurrentUser\Root | Select-Object Subject, Thumbprint
   ```

3. **Re-download VPN client** (ensures it matches current gateway configuration):
   - Azure Portal → Virtual Network Gateway
   - Point-to-site configuration → Download VPN client
   - Run the installer again

#### Error: OpenSSL command not found
**Symptom**: Certificate installation script fails with "openssl is not recognized"

**Solution**:
```powershell
# Install OpenSSL
winget install FireDaemon.OpenSSL

# Restart PowerShell session to reload PATH
# Then re-run certificate installation
```

#### Error: Certificate expires immediately
**Symptom**: Certificates show as expired or have invalid dates

**Solution**:
1. Check system time is correct
2. Redeploy Terraform to generate new certificates:
   ```bash
   terraform taint tls_self_signed_cert.vpn_root_ca[0]
   terraform taint tls_locally_signed_cert.vpn_client[0]
   terraform apply
   ```
3. Reinstall certificates

### VPN Gateway Creation Fails
**Symptom**: Gateway deployment times out or fails

**Solutions**:
- Verify quota for VPN Gateways in your region
- Try a different region
- Check for any Azure service outages
- Gateway creation takes 30-45 minutes - be patient

### Cannot Connect to VPN
**Symptom**: VPN client shows "Connection failed"

**Root Cause Checklist**:
1. ❌ Certificates not installed → See [Certificate Installation Issues](#certificate-installation-issues)
2. ❌ VPN client not downloaded/installed → See [Step 2: Download and Install VPN Client](#step-2-download-and-install-vpn-client)
3. ❌ Wrong VPN client package → Re-download from Azure Portal
4. ❌ Gateway not ready → Check status in Portal

**Solutions**:
1. **Verify certificates are installed** (most common issue):
   ```powershell
   Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object {$_.Subject -like "*vpn-client*"}
   Get-ChildItem -Path Cert:\CurrentUser\Root | Where-Object {$_.Subject -like "*vpn-root-ca*"}
   ```

2. **Check VPN Gateway status**:
   ```bash
   az network vnet-gateway show \
     --resource-group $(terraform output -raw resource_group_name) \
     --name $(terraform output vpn_gateway_id | rev | cut -d'/' -f1 | rev) \
     --query "provisioningState"
   # Should return: "Succeeded"
   ```

3. **Re-download VPN client** (ensures it matches current gateway configuration):
   - Azure Portal → Virtual Network Gateways → Your Gateway
   - Point-to-site configuration → Download VPN client
   - Reinstall the client

4. **Check Windows Event Logs** (for detailed error messages):
   ```powershell
   Get-WinEvent -LogName "Microsoft-Windows-NetworkProfile/Operational" -MaxEvents 20 | 
     Where-Object {$_.Message -like "*VPN*"} | 
     Format-List TimeCreated, Message
   ```

### DNS Resolution Not Working
**Symptom**: Cannot resolve private endpoint names or DNS queries timing out

**Root Cause**: DNS Server role is not installed on the DNS VM. The DNS Server role is installed via a separate post-deployment script (`install-dns-server.ps1`), NOT during Terraform deployment.

**Solution - Run the DNS installation script**:

```powershell
# Run the DNS installation script (post-deployment)
cd hub-spoke-network
.\install-dns-server.ps1

# This will:
# - Install DNS Server role via az vm run-command
# - Configure DNS forwarder to 168.63.129.16
# - Create conditional forwarders for 12 Azure zones
# - Log operations to C:\dns-install.log on the VM
```

**Verify DNS Server is installed**:
```powershell
# Check DNS Server role status on the VM
az vm run-command invoke \
  --resource-group $(terraform output -raw resource_group_name) \
  --name $(terraform output -raw dns_vm_name) \
  --command-id RunPowerShellScript \
  --scripts "Get-WindowsFeature DNS"

# Should show: Install State: Installed
```

**Verify conditional forwarders**:
```powershell
# Connect to VPN first, then RDP to 10.0.1.4
# On the DNS VM, run:
Get-DnsServerZone | Where-Object {$_.ZoneType -eq "Forwarder"} | Select-Object ZoneName

# Should show 12 zones:
# - services.ai.azure.com
# - api.azureml.ms
# - notebooks.azure.net
# - blob.core.windows.net
# - file.core.windows.net
# - table.core.windows.net
# - queue.core.windows.net
# - cognitiveservices.azure.com
# - openai.azure.com
# - documents.azure.com
# - search.windows.net
# - vaultcore.azure.net
```

**Test DNS resolution manually**:
```powershell
# Test from your client machine (connected to VPN)
nslookup privatelink.cognitiveservices.azure.com 10.0.1.4
nslookup services.ai.azure.com 10.0.1.4

# Should show: Server: vm-dns-XXXXX (10.0.1.4)
```

**Additional checks**:
1. Verify VNets are configured with custom DNS (10.0.1.4):
   ```bash
   az network vnet show --resource-group $(terraform output -raw resource_group_name) \
     --name $(terraform output -raw hub_vnet_name) \
     --query "dhcpOptions.dnsServers"
   ```

2. Check DNS VM is running:
   ```bash
   az vm show --resource-group $(terraform output -raw resource_group_name) \
     --name $(terraform output -raw dns_vm_name) \
     --query "powerState"
   ```

3. Check DNS installation logs on the VM (via RDP):
   ```powershell
   Get-Content C:\dns-install.log
   Get-Content C:\dns-config.log
   ```

### Cannot RDP to DNS VM
**Symptom**: RDP connection times out

**Solutions**:
1. Verify you're connected to VPN first
2. Check NSG allows RDP from VPN client pool (172.16.0.0/24)
3. Verify DNS VM is running in Azure Portal
4. Ping the DNS VM IP: `ping 10.0.1.4`

### Private Endpoints Not Resolving
**Symptom**: Private endpoints resolve to public IPs instead of private IPs

**Solutions**:
1. Ensure VNets are using custom DNS (10.0.1.4)
2. Restart VMs/services to pick up new DNS settings
3. Clear DNS cache on client:
   ```bash
   # Windows
   ipconfig /flushdns
   
   # Linux/Mac
   sudo dscacheutil -flushcache
   ```
4. Verify Private DNS Zone links are active

### VM Size Not Available in Region
**Symptom**: Terraform deployment fails with one of these errors:
```
InvalidParameter: The value Standard_D2s_v3 provided for the VM size is not valid.
The valid sizes in the current region are: Standard_D2a_v4, Standard_D4a_v4...
```
or
```
InvalidParameter: Requested operation cannot be performed because the VM size Standard_D2a_v4 
does not support the storage account type Premium_LRS of disk 'vm-dns-osdisk'.
```

**Solution**:
1. Edit `terraform.tfvars` and change the `dns_vm_size` variable to a compatible size
2. **Important**: The VM size must support Premium_LRS storage (look for "s" in the name)
3. Recommended alternatives (2 vCPU, 8GB RAM, Premium storage support):
   ```hcl
   dns_vm_size = "Standard_D2s_v3"   # Intel-based, Premium storage
   # or
   dns_vm_size = "Standard_D2as_v5"  # AMD-based, Premium storage, good price/performance
   # or
   dns_vm_size = "Standard_D2s_v5"   # Intel-based Gen5, Premium storage
   ```
4. Run `terraform apply` again

**Note about VM sizes**:
- VM sizes **with** "s" (like D2**s**_v3, D2a**s**_v5) = Support Premium storage ✅
- VM sizes **without** "s" (like D2_v3, D2a_v4) = Standard storage only ❌
- Check [Azure VM sizes by region](https://azure.microsoft.com/en-us/explore/global-infrastructure/products-by-region/) for availability in your region

### High Costs
**Symptom**: Monthly bill higher than expected

**Solutions**:
- VPN Gateway is the primary cost driver (~$260/month for VpnGw2)
- Consider VpnGw1 ($130/month) for non-production environments
- Stop DNS VM when not in use
- Use reserved instances for long-term deployments

## Additional Resources

- [Azure Virtual Network Documentation](https://docs.microsoft.com/en-us/azure/virtual-network/)
- [Azure VPN Gateway Documentation](https://docs.microsoft.com/en-us/azure/vpn-gateway/)
- [Azure Private Link Documentation](https://docs.microsoft.com/en-us/azure/private-link/)
- [Azure Private DNS Documentation](https://docs.microsoft.com/en-us/azure/dns/private-dns-overview)
- [Azure AI Foundry Documentation](https://learn.microsoft.com/en-us/azure/ai-studio/)

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section above
2. Review Terraform logs: `terraform apply -debug`
3. Check Azure Activity Log in Portal for deployment errors
4. Open an issue in the repository

---

**Next Steps**: After deploying this infrastructure, proceed to the [18-managed-virtual-network-preview](../18-managed-virtual-network-preview/README.md) module to deploy Azure AI Foundry with managed virtual network.
