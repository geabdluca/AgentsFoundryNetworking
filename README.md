# Azure AI Foundry Network Deployer

One-click deployment solution for Azure AI Foundry with full network isolation using a hub-spoke topology.

## Overview

This project provides an automated launcher that deploys a complete, production-ready Azure AI Foundry environment with:

- **Hub-Spoke Network** - VPN Gateway, DNS Server, Private DNS Zones
- **AI Foundry Resources** - AI Foundry Account, Cosmos DB, AI Search, Storage
- **Private Connectivity** - All resources secured with Private Endpoints
- **VPN Access** - Point-to-Site VPN for secure remote access

## Quick Start

### Prerequisites

- **Windows 10/11** with PowerShell
- **Python 3.8+** 
- **Terraform** - `winget install Hashicorp.Terraform`
- **Azure CLI** - `winget install Microsoft.AzureCLI`
- **Azure Subscription** with Owner/Contributor permissions

```powershell
# Login to Azure
az login
```

### Run the Launcher

```powershell
# Create virtual environment (first time only)
python -m venv hublauncher_v0.1.0

# Activate and run
.\hublauncher_v0.1.0\Scripts\Activate.ps1
python launcher.py
```

The launcher presents a menu-driven interface:

```
================================================================
         Azure AI Foundry Network Deployer v1.0                 
================================================================

=== Main Menu ===

  Options:
    [1] Deploy - Start or resume deployment
    [2] Destroy - Remove deployed resources
    [0] Quit

  Select option:
```

---

## Launcher Features

### Deploy Workflow

The **Deploy** option guides you through a 7-step automated deployment:

| Step | Description | Duration |
|------|-------------|----------|
| 1 | Prerequisites Check | ~10 sec |
| 2 | Configuration (subscription, region, firewall) | Interactive |
| 3 | Deploy Hub-Spoke Network | 45-60 min |
| 4 | Configure DNS Server | ~2 min |
| 5 | Install VPN Certificates | ~30 sec |
| 6 | Install VPN Client (optional) | ~2 min |
| 7 | Deploy AI Foundry (BYO VNet) | 20-30 min |

**Features:**
- Automatic retry on transient failures
- Resume capability - restart from where you left off
- Progress saved to `.deployment-state.json`
- Detailed logging in `logs/` folder

### Destroy Workflow

The **Destroy** option provides safe cleanup with two modes:

| Option | Description |
|--------|-------------|
| **BYO VNet Only** | Remove AI Foundry resources, keep hub-spoke network for reuse |
| **Destroy ALL** | Remove everything (AI Foundry + Hub-Spoke Network) |

**Features:**
- Automatic Cognitive Services purge (handles soft-delete)
- VPN client and connection cleanup
- Terraform state cleanup (keeps provider cache for speed)
- Fallback to resource group deletion if terraform destroy fails

### State Management

The launcher tracks deployment progress in `.deployment-state.json`:

```json
{
  "subscription_id": "...",
  "location": "eastus",
  "steps": {
    "hub_spoke": {"status": "completed"},
    "dns_install": {"status": "completed"},
    "byo_vnet": {"status": "pending"}
  }
}
```

This enables:
- Resume interrupted deployments
- Know what's deployed for cleanup
- Skip already-completed steps

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Hub VNet (10.0.0.0/16)                   │
│   ┌──────────────┐              ┌─────────────────┐        │
│   │ VPN Gateway  │              │    DNS VM       │        │
│   │   (P2S)      │              │   10.0.1.4      │        │
│   └──────────────┘              └─────────────────┘        │
└────────────────────────────────┬────────────────────────────┘
                                 │ VNet Peering
┌────────────────────────────────▼────────────────────────────┐
│                  Spoke VNet (10.1.0.0/16)                   │
│   ┌──────────────────┐         ┌──────────────────┐        │
│   │ Private Endpoints│         │ Agents Subnet    │        │
│   │ Subnet           │         │ (Delegated)      │        │
│   └──────────────────┘         └──────────────────┘        │
└────────────────────────────────┬────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────┐
│              AI Foundry Resources (New RG)                  │
│                                                             │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐  │
│  │ AI Foundry│ │ Cosmos DB │ │ AI Search │ │  Storage  │  │
│  │ + Project │ │           │ │           │ │  Account  │  │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
AgentsFoundryNetworking/
├── launcher.py                 # Main launcher application
├── .deployment-state.json      # Deployment state (auto-generated)
├── logs/                       # Deployment logs (auto-generated)
│
├── hub-spoke-network/          # Network infrastructure module
│   ├── README.md               # Detailed network documentation
│   ├── install-dns-server.ps1  # DNS configuration script
│   ├── install-vpn-certs.ps1   # VPN certificate script
│   └── code/                   # Terraform code
│
└── byo-vnet/                   # AI Foundry resources module
    ├── README.md               # AI Foundry documentation
    └── code/                   # Terraform code
```

---

## Documentation

| Module | Description |
|--------|-------------|
| **[Hub-Spoke Network](./hub-spoke-network/README.md)** | Network infrastructure, VPN setup, DNS configuration |
| **[BYO VNet AI Foundry](./byo-vnet/README.md)** | AI Foundry resources, private endpoints, custom VNet option |

---

## Estimated Costs

| Resource | Monthly Cost |
|----------|-------------|
| VPN Gateway (VpnGw2) | ~$260 |
| DNS VM (D2s_v3) | ~$70 |
| AI Search (Standard) | ~$250 |
| Cosmos DB | ~$25 |
| Storage Account | ~$5 |
| Azure Firewall *(optional)* | ~$900 |
| **Total** | **~$610/month** (or ~$1,510 with firewall) |

---

## Manual Deployment

If you prefer manual deployment over the launcher, see the individual module READMEs:

1. [Hub-Spoke Network Manual Setup](./hub-spoke-network/README.md#quick-start)
2. [BYO VNet AI Foundry Manual Setup](./byo-vnet/README.md)

---

## Troubleshooting

### Launcher Issues

| Issue | Solution |
|-------|----------|
| Prerequisites check fails | Run `az login` and verify tools with `terraform --version` |
| Deployment stuck | Check `logs/deploy-*.log` for errors, use Ctrl+C and re-run to resume |
| VPN certificates fail | Run launcher as Administrator for certificate installation |
| Destroy fails | Check if resources were already deleted in Azure Portal |
| BYO VNet deployment fails repeatedly | **Use Destroy option before retrying** - Azure operations may be stuck in a pending state that Terraform cannot recover from. Run Destroy (option 2) to clean up, then Deploy fresh. |

### Module-Specific Issues

- [Hub-Spoke Troubleshooting](./hub-spoke-network/README.md#troubleshooting)
- [BYO VNet Troubleshooting](./byo-vnet/README.md#troubleshooting)

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## License

MIT License - see LICENSE file for details.
