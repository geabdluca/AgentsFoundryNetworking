# Hub-Spoke Network Infrastructure for Azure AI Foundry

This Terraform module creates a complete hub-spoke network architecture to support Azure AI Foundry deployments with managed virtual networks. This infrastructure is designed for organizations that need to establish network connectivity before deploying AI Foundry resources.

## � Quick Start

Get your infrastructure deployed in under 60 minutes:

### 1. Prerequisites
```powershell
# Install required tools
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
.\fix-vpn-certificates.ps1

# Download VPN client from Azure Portal:
# Navigate to VPN Gateway > Point-to-site configuration > Download VPN client

# Install VPN client and connect
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
- ✅ VPN connectivity established
- ✅ DNS resolution configured
- ✅ Private DNS zones linked
- ✅ Network secured with NSGs

---

## �📋 Table of Contents

- [Quick Start Checklist](#quick-start-checklist)
- [Overview](#overview)
- [Architecture](#architecture)
- [When to Use This Module](#when-to-use-this-module)
- [Components](#components)
- [Prerequisites](#prerequisites)
- [Deployment Steps](#deployment-steps)
- [Post-Deployment Configuration](#post-deployment-configuration)
- [Integration with AI Foundry](#integration-with-ai-foundry)
- [Cleanup](#cleanup)
- [Troubleshooting](#troubleshooting)

## Quick Start Checklist

Follow this checklist for a successful deployment:

### Before Deployment
- [ ] **Install Required Tools** (see [Prerequisites](#required-tools-installation))
  - [ ] Terraform >= 1.0
  - [ ] Azure CLI >= 2.40
  - [ ] OpenSSL (for certificate installation)
  - [ ] PowerShell 7+ (recommended)
- [ ] **Login to Azure**: `az login`
- [ ] **Set Subscription**: `az account set --subscription "YOUR-ID"`
- [ ] **Configure terraform.tfvars** with your values

### Deployment (45-60 minutes)
- [ ] **Initialize**: `terraform init`
- [ ] **Review Plan**: `terraform plan`
- [ ] **Deploy**: `terraform apply`
- [ ] **Wait for VPN Gateway** (30-45 minutes)

### After Deployment - VPN Setup (Follow in Order!)
- [ ] **Step 1: Install Certificates** (see [Step 1](#step-1-install-vpn-client-certificates))
  ```powershell
  # Export and install certificates to CurrentUser stores
  terraform output -raw vpn_client_certificate_pem > cert.pem
  terraform output -raw vpn_client_private_key_pem > key.pem
  terraform output -raw vpn_root_certificate_pem > rootca.pem
  .\fix-vpn-certificates.ps1
  ```
- [ ] **Verify Certificates**: Check both client cert and root CA are in CurrentUser stores
- [ ] **Step 2: Download VPN Client** from Azure Portal
- [ ] **Step 3: Install VPN Client** (run installer)
- [ ] **Step 4: Connect to VPN** (should use certificates automatically)
- [ ] **Step 5: Install DNS Server** (see [Step 5](#step-5-install-dns-server-post-deployment))
  ```powershell
  .\install-dns-server.ps1
  ```
- [ ] **Step 6: Test DNS**: `nslookup privatelink.services.ai.azure.com 10.0.1.4`

### Ready for AI Foundry
- [ ] VPN connected and DNS resolution working
- [ ] Proceed to deploy AI Foundry resources

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

## When to Use This Module

✅ **Use this module when:**
- You need to create network infrastructure from scratch
- You require VPN access to Azure resources for development/testing
- You want centralized DNS management for hybrid environments
- You need to establish connectivity before deploying AI Foundry

❌ **Skip this module if:**
- You already have an existing VNet infrastructure
- You're using Azure-native DNS without custom requirements
- You don't need VPN connectivity

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

## Deployment Steps

### Step 1: Clone and Navigate
```bash
cd hub-spoke-network
```

### Step 2: Configure Variables
Copy the example variables file:
```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:
```hcl
subscription_id      = "YOUR-SUBSCRIPTION-ID"
resource_group_name  = "rg-aifoundry-hubspoke"
location             = "eastus"

# Optional: Customize VNet address spaces
hub_vnet_address_space                = "10.0.0.0/16"
spoke_vnet_address_space              = "10.1.0.0/16"

# Optional: Customize VPN settings
vpn_gateway_sku         = "VpnGw2"
vpn_client_address_pool = ["172.16.0.0/24"]

# Optional: Customize DNS VM
dns_vm_size = "Standard_D2s_v3"
```

### Step 3: Initialize Terraform
```bash
terraform init
```

### Step 4: Review the Plan
```bash
terraform plan
```

Review the resources that will be created. You should see approximately 40-50 resources.

### Step 5: Deploy
```bash
terraform apply
```

Type `yes` when prompted. The deployment will take 45-60 minutes due to VPN Gateway creation.

⚠️ **Note**: Terraform will deploy the DNS VM but will NOT install the DNS Server role. DNS installation is done via a separate post-deployment script for reliability.

### Step 6: Capture Outputs
Once deployment completes, save important outputs:

```bash
# Save all outputs
terraform output > deployment-info.txt

# Get DNS VM password (optional - only needed if you want to RDP to the VM)
terraform output -raw dns_vm_admin_password

# VPN certificates are exported automatically by the post-deployment scripts
```

## Post-Deployment Configuration

⚠️ **CRITICAL**: Complete these steps IN ORDER after Terraform deployment:

1. **Install VPN Certificates** (Step 1)
2. **Download & Install VPN Client** (Step 2)  
3. **Connect to VPN** (Step 3)
4. **Install DNS Server** (Step 5)
5. **Test DNS Resolution** (Step 6)

⚠️ **IMPORTANT**: Follow these steps in order for successful VPN connectivity.

### Step 1: Install VPN Client Certificates

The VPN uses certificate-based authentication. You must install the certificates **before** downloading the VPN client.

#### Prerequisites for Certificate Installation
Ensure you have the following installed (see [Prerequisites](#required-tools-installation)):
- ✅ PowerShell 7+
- ✅ OpenSSL (for certificate conversion)

#### Install Certificates (Windows)

**Using the Certificate Fix Script (Recommended)**

This script properly installs certificates to CurrentUser stores (required by Windows VPN client):

```powershell
# Navigate to the Terraform directory
cd hub-spoke-network

# Export certificates to temporary files
terraform output -raw vpn_client_certificate_pem > cert.pem
terraform output -raw vpn_client_private_key_pem > key.pem
terraform output -raw vpn_root_certificate_pem > rootca.pem

# Run the certificate installation script
.\fix-vpn-certificates.ps1

# The script will:
# - Clean up old certificates from previous deployments
# - Install Root CA to CurrentUser\Root
# - Install Client certificate with private key to CurrentUser\My
# - Verify installation and thumbprints
```

**Verification:**
```powershell
# Verify client certificate is installed (should have private key)
Get-ChildItem Cert:\CurrentUser\My | Where-Object {$_.Subject -like "*vpn-client*"} | Select-Object Subject, Thumbprint, HasPrivateKey

# Verify root CA is installed
Get-ChildItem Cert:\CurrentUser\Root | Where-Object {$_.Subject -like "*vpn-root-ca*"} | Select-Object Subject, Thumbprint
```

You should see both certificates with the client certificate showing `HasPrivateKey : True`.

**Option B: Manual Installation**

If the automated script fails, you can manually install using OpenSSL:

```powershell
# Export certificates
terraform output -raw vpn_client_certificate_pem > client.crt
terraform output -raw vpn_client_private_key_pem > client.key
terraform output -raw vpn_root_certificate_pem > root.crt

# Convert to PFX format using OpenSSL
openssl pkcs12 -export -out client.pfx -inkey client.key -in client.crt -password pass:

# Import client certificate
Import-PfxCertificate -FilePath client.pfx -CertStoreLocation Cert:\LocalMachine\My -Exportable

# Import root CA
Import-Certificate -FilePath root.crt -CertStoreLocation Cert:\LocalMachine\Root

# Clean up
Remove-Item client.crt, client.key, root.crt, client.pfx
```

#### Install Certificates (Mac/Linux)

**macOS:**
```bash
# Export certificates
terraform output -raw vpn_client_certificate_pem > client.crt
terraform output -raw vpn_client_private_key_pem > client.key
terraform output -raw vpn_root_certificate_pem > root.crt

# Convert to P12 format
openssl pkcs12 -export -out client.p12 -inkey client.key -in client.crt -certfile root.crt

# Import to Keychain (will prompt for password)
security import client.p12 -k ~/Library/Keychains/login.keychain

# Clean up
rm client.crt client.key root.crt client.p12
```

⚠️ **Important for Windows VPN Clients**: The VPN client requires certificates to be installed in the **CurrentUser** certificate stores, NOT LocalMachine stores. Use the `fix-vpn-certificates.ps1` script which properly installs certificates to CurrentUser\My and CurrentUser\Root stores.

**Windows (Recommended):**
```powershell
# Export certificates from Terraform outputs
terraform output -raw vpn_client_certificate_pem > cert.pem
terraform output -raw vpn_client_private_key_pem > key.pem
terraform output -raw vpn_root_certificate_pem > rootca.pem

# Install certificates to CurrentUser stores (fixes Error 798)
.\fix-vpn-certificates.ps1

# Verify installation
Get-ChildItem Cert:\CurrentUser\My | Where-Object {$_.Subject -like "*vpn-client*"}
Get-ChildItem Cert:\CurrentUser\Root | Where-Object {$_.Subject -like "*vpn-root-ca*"}
```

**Linux:**
```bash
# Export certificates
terraform output -raw vpn_client_certificate_pem > client.crt
terraform output -raw vpn_client_private_key_pem > client.key
terraform output -raw vpn_root_certificate_pem > root.crt

# Copy to OpenVPN config directory
sudo mkdir -p /etc/openvpn/client
sudo cp client.crt /etc/openvpn/client/
sudo cp client.key /etc/openvpn/client/
sudo cp root.crt /etc/openvpn/client/

# Set permissions
sudo chmod 600 /etc/openvpn/client/*.key
```

### Step 2: Download and Install VPN Client

⚠️ **Only proceed after certificates are installed successfully!**

#### Get VPN Gateway Information
```bash
# Get VPN Gateway name
terraform output -raw vpn_gateway_id

# Get VPN Gateway public IP
terraform output -raw vpn_gateway_public_ip
```

#### Download VPN Client Configuration

**Using Azure Portal:**
1. Navigate to **Azure Portal** → **Virtual Network Gateways**
2. Select your VPN Gateway (name from terraform output)
3. Go to **Point-to-site configuration**
4. Click **Download VPN client**
5. Extract the downloaded ZIP file

**Using Azure CLI:**
```bash
# Get resource group and gateway name
RG_NAME=$(terraform output -raw resource_group_name)
GW_NAME=$(terraform output vpn_gateway_id | rev | cut -d'/' -f1 | rev)

# Generate VPN client package
az network vnet-gateway vpn-client generate \
  --resource-group $RG_NAME \
  --name $GW_NAME \
  --processor-architecture Amd64

# Download will provide a URL - download and extract
```

#### Install VPN Client

**Windows:**
```powershell
# Extract the downloaded ZIP file
# Navigate to the WindowsAmd64 or WindowsX86 folder
# Run VpnClientSetupAmd64.exe (or VpnClientSetupX86.exe)
.\VpnClientSetupAmd64.exe
```

**Mac:**
- Use the **Generic** folder from the ZIP
- Import the `.ovpn` configuration file into your OpenVPN client
- Recommended client: [Tunnelblick](https://tunnelblick.net/)

**Linux:**
- Use the **Generic** folder from the ZIP
- Configure with OpenVPN: `sudo openvpn --config Generic/vpnconfig.ovpn`

### Step 3: Connect to VPN

**Windows:**
1. Click the **Network** icon in system tray
2. Select **VPN** → Find your connection (usually shows gateway name)
3. Click **Connect**
4. Authentication will use the certificate automatically

**Mac/Linux:**
1. Open your OpenVPN client
2. Select the imported profile
3. Click **Connect**

**Verify Connection:**
```powershell
# Check your VPN IP address (should be from 172.16.0.0/24 pool)
ipconfig (Windows)
ifconfig (Mac/Linux)

# Test connectivity to DNS VM
ping 10.0.1.4

# Test DNS resolution
nslookup google.com 10.0.1.4
```

### Step 4: Configure VNet DNS Settings

Both VNets need to be configured to use the custom DNS server for proper private endpoint resolution.

⚠️ **Note**: The Terraform deployment already configured the VNets with `dns_servers = ["10.0.1.4"]`. This step is included for reference and troubleshooting.

#### Verify DNS Configuration

**Using Azure CLI:**
```bash
# Get resource group and VNet names
RG_NAME=$(terraform output -raw resource_group_name)
HUB_VNET=$(terraform output -raw hub_vnet_name)
SPOKE_VNET=$(terraform output -raw spoke_vnet_name)

# Check Hub VNet DNS settings
az network vnet show --resource-group $RG_NAME --name $HUB_VNET --query "dhcpOptions.dnsServers"

# Check Spoke VNet DNS settings
az network vnet show --resource-group $RG_NAME --name $SPOKE_VNET --query "dhcpOptions.dnsServers"

# Should show: ["10.0.1.4"]
```

#### Update DNS Settings (if needed)

**Using Azure Portal:**
1. Navigate to **Azure Portal** → **Virtual Networks**
2. Select **Hub VNet** → **DNS servers**
3. Choose **Custom** and enter: `10.0.1.4`
4. Click **Save**
5. Repeat for **Spoke VNet**

**Using Azure CLI:**
```bash
# Update Hub VNet DNS (if needed)
az network vnet update \
  --resource-group $RG_NAME \
  --name $HUB_VNET \
  --dns-servers 10.0.1.4

# Update Spoke VNet DNS (if needed)
az network vnet update \
  --resource-group $RG_NAME \
  --name $SPOKE_VNET \
  --dns-servers 10.0.1.4
```

### Step 5: Install DNS Server (Post-Deployment)

⚠️ **Important**: Due to limitations with CustomScriptExtension, the DNS Server role is NOT automatically installed during Terraform deployment. You must run the separate installation script after deployment completes.

#### Why a Separate Script?

The Terraform `azurerm_virtual_machine_extension` with inline PowerShell commands can fail silently when:
- Scripts are too long or complex
- Multiple restarts are required
- Verbose output exceeds extension limits

Using a separate script with `az vm run-command` provides:
- ✅ Reliable execution with proper error handling
- ✅ Real-time progress output
- ✅ Detailed logging on the VM
- ✅ Easy re-run capability if needed

#### Install DNS Server Role

```powershell
# Run the DNS installation script
.\install-dns-server.ps1
```

**What the script does:**
1. Retrieves resource group and VM name from Terraform outputs
2. Installs DNS Server role on the Windows VM
3. Configures DNS forwarder to Azure DNS (168.63.129.16)
4. Creates conditional forwarders for 12 Azure Private DNS zones:
   - services.ai.azure.com
   - api.azureml.ms
   - notebooks.azure.net
   - blob.core.windows.net
   - file.core.windows.net
   - table.core.windows.net
   - queue.core.windows.net
   - cognitiveservices.azure.com
   - openai.azure.com
   - documents.azure.com
   - search.windows.net
   - vaultcore.azure.net
5. Logs all operations to C:\dns-install.log and C:\dns-config.log on the VM

**Expected output:**
```
=== DNS Server Installation ===
Resource Group: rg-aifoundry-hubspoke-XXXXX
VM Name: vm-dns-XXXXX

Installing DNS Server role...
✓ DNS Server role installed successfully

Configuring DNS forwarder...
✓ DNS forwarder configured to 168.63.129.16

Creating conditional forwarders...
✓ Created conditional forwarder for services.ai.azure.com
✓ Created conditional forwarder for api.azureml.ms
...

=== DNS Installation Complete ===
Check logs on VM:
- C:\dns-install.log
- C:\dns-config.log
```

**Installation time**: 3-5 minutes

#### Verify DNS Installation

```powershell
# Check if DNS commands run successfully
az vm run-command invoke \
  --resource-group $(terraform output -raw resource_group_name) \
  --name $(terraform output -raw dns_vm_name) \
  --command-id RunPowerShellScript \
  --scripts "Get-WindowsFeature DNS" "Get-DnsServerForwarder" "Get-DnsServerZone | Where-Object {\$_.ZoneType -eq 'Forwarder'}"
```

### Step 6: Verify DNS Resolution Through VPN

After connecting to VPN and installing DNS Server, test DNS resolution:

```powershell
# Test Azure DNS zones (explicitly use DNS VM)
nslookup privatelink.cognitiveservices.azure.com 10.0.1.4
nslookup privatelink.openai.azure.com 10.0.1.4
nslookup privatelink.services.ai.azure.com 10.0.1.4
nslookup privatelink.blob.core.windows.net 10.0.1.4

# All should resolve through 10.0.1.4
# Response should show: Server: vm-dns-XXXX (10.0.1.4)
```

**Expected Output:**
```
Server:  vm-dns-fcc7a868
Address:  10.0.1.4

Non-authoritative answer:
Name:    privatelink.cognitiveservices.azure.com
Address:  (Empty - no records yet, this is normal before deploying services)
```

### Step 7: Verify DNS VM Configuration (Optional)

#### RDP to DNS VM
1. **Ensure you're connected to VPN first**
2. Open Remote Desktop Connection
3. Connect with:
   - **Host**: `10.0.1.4`
   - **Username**: `azureuser` (or check: `terraform output -raw dns_vm_admin_username`)
   - **Password**: `terraform output -raw dns_vm_admin_password`

#### Verify DNS Configuration
Once logged in to the DNS VM, run these PowerShell commands:

```powershell
# Check DNS Server role is installed
Get-WindowsFeature DNS

# Verify forwarders (should show 168.63.129.16)
Get-DnsServerForwarder

# Check all conditional forwarders (should show 12 zones)
Get-DnsServerZone | Where-Object {$_.ZoneType -eq "Forwarder"} | Select-Object ZoneName

# Expected output: All 12 private DNS zones
# - privatelink.services.ai.azure.com
# - privatelink.api.azureml.ms
# - privatelink.notebooks.azure.net
# - privatelink.blob.core.windows.net
# - privatelink.file.core.windows.net
# - privatelink.table.core.windows.net
# - privatelink.queue.core.windows.net
# - privatelink.cognitiveservices.azure.com
# - privatelink.openai.azure.com
# - privatelink.documents.azure.com
# - privatelink.search.windows.net
# - privatelink.vaultcore.azure.net

# Test Azure DNS resolution
nslookup privatelink.cognitiveservices.azure.com 168.63.129.16
nslookup privatelink.services.ai.azure.com 168.63.129.16
```

#### Check DNS Configuration Log
```powershell
# View the configuration completion log
Get-Content C:\dns-config-completed.log
```

This should show a timestamp indicating when the DNS configuration completed successfully.

## Integration with AI Foundry

After deploying this hub-spoke network, you can deploy AI Foundry with managed VNet using the values from this deployment.

### Get Required Values
```bash
# Spoke VNet ID (for managed VNet configuration)
terraform output -raw spoke_vnet_id

# Spoke delegated subnet ID
terraform output -raw spoke_delegated_subnet_id

# Private DNS Zone IDs
terraform output -json private_dns_zone_ids
```

### Deploy AI Foundry
Navigate to the managed VNet template directory:

```bash
cd ../18-managed-virtual-network-preview
```

Update your `terraform.tfvars` with:
```hcl
# Enable integration with hub-spoke network
use_existing_network = true
existing_vnet_id     = "<spoke_vnet_id from hub-spoke output>"
existing_subnet_id   = "<spoke_private_endpoints_subnet_id from hub-spoke output>"

# Optional: Use existing Private DNS Zones
use_existing_private_dns_zones = true
existing_private_dns_zone_ids = {
  cognitive           = "<id>"
  openai              = "<id>"
  blob_storage        = "<id>"
  # ... copy from hub-spoke outputs
}

# Enable required services
enable_storage = true
enable_aisearch = true
enable_cosmos = true
```

Then deploy:
```bash
terraform init
terraform apply
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

This script properly installs certificates to the correct stores and cleans up old certificates:

```powershell
# Export certificates from Terraform
cd hub-spoke-network
terraform output -raw vpn_client_certificate_pem > cert.pem
terraform output -raw vpn_client_private_key_pem > key.pem
terraform output -raw vpn_root_certificate_pem > rootca.pem

# Run the fix script (handles everything automatically)
.\fix-vpn-certificates.ps1

# The script will:
# 1. Clean up old VPN certificates from previous deployments
# 2. Remove old VPN client profiles
# 3. Install Root CA to CurrentUser\Root
# 4. Install Client cert with private key to CurrentUser\My
# 5. Verify installation
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
   Get-ChildItem -Path Cert:\LocalMachine\My | Where-Object {$_.Subject -like "*P2SClientCert*"}
   Get-ChildItem -Path Cert:\LocalMachine\Root | Where-Object {$_.Subject -like "*P2SRootCert*"}
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
