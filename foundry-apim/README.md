# AI Foundry (BYO VNet) + API Management

> **⚠ Work In Progress (WIP)**
> This scenario deploys successfully but **DNS resolution for the APIM gateway endpoint is not yet fully working** from within the VNet. The AI Foundry resources, capability host, and APIM instance are deployed correctly; the outstanding issue is private DNS resolution for the APIM internal VNet URL. This is actively being investigated and will be resolved before this scenario is considered production-ready.

Deploys a complete AI Foundry stack into the hub-spoke spoke VNet and adds **Azure API Management (Developer SKU, internal VNet mode)** for controlled, private access to the AI Foundry endpoint.

## Overview

This module builds on top of the hub-spoke network deployed by the launcher. It provisions:

- **AI Foundry account** (private endpoint, no public access)
- **AI Foundry project** with Standard Agent capability host (VNet-injected)
- **Storage Account**, **Cosmos DB**, **AI Search** — all with private endpoints
- **API Management** (Developer SKU, internal VNet mode) — proxies the AI Foundry API through a subnet in the spoke VNet
- **NSG** with the mandatory rules required by APIM internal VNet integration

## Prerequisites

The **Hub-Spoke Network** must be fully deployed before running this module. The launcher enforces this order automatically.

## Publisher Info (Automatic)

The APIM `publisher_name` and `publisher_email` are automatically populated from your logged-in Azure account (`az account show`) by the launcher. You do not need to set these manually.

> If the logged-in user principal name (UPN) does not look like an email address, the launcher constructs a placeholder email (`<name>@example.com`). You can override this by setting `apim_publisher_email` manually in `terraform.tfvars`.

## APIM SKU

This module defaults to the **Developer** SKU, which:
- Supports internal VNet integration
- Has **no SLA** — suitable for labs and demos
- Costs approximately **~$50/month**

For production use, upgrade to **Standard** or **Premium** (requires changing `apim_sku` in variables).

## Architecture

```
Hub VNet (10.0.0.0/16)
  └── (peered)
Spoke VNet (10.1.0.0/16)
  ├── snet-privateendpoints (10.1.0.0/24)  ← Private endpoints for all services
  ├── snet-agents           (10.1.1.0/24)  ← AI Foundry agent delegation
  └── snet-apim             (10.1.2.0/24)  ← API Management (internal VNet)
        └── apim-foundry-<suffix>
              └── ai-foundry-api → AI Foundry account endpoint
```

## Resource Group

All resources are deployed into a single resource group (`rg-aifoundry-apim` by default), separate from the hub-spoke resource group. This allows the APIM + Foundry stack to be destroyed independently without touching the network.

## Manual Deployment

If you prefer to deploy manually without the launcher:

```powershell
cd foundry-apim/code
cp example.tfvars terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
terraform apply
```

## Destroy

Use the launcher's **Destroy** option:
- **Option 1**: `Destroy AI Foundry + APIM only` — removes the foundry + APIM resource group, purges soft-deleted Cognitive Services, cleans Terraform state. Hub-Spoke network is preserved.
- **Option 2**: `Destroy ALL` — destroys everything (APIM + Foundry first, then Hub-Spoke).

## Estimated Additional Cost

| Resource | Monthly Cost |
|----------|-------------|
| API Management (Developer) | ~$50 |
| (Plus all standard Foundry costs) | See main README |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| APIM deployment times out | APIM internal VNet deployment can take 30-45 min. Let it complete. |
| APIM NSG errors | The NSG rules in this module are mandatory for internal VNet mode. Do not remove them. |
| `gateway_url` not reachable | APIM internal VNet mode is only accessible from within the VNet (via VPN). Connect first. |
| AI Foundry capability host fails | Ensure hub-spoke is fully deployed and the APIM subnet exists before retrying. |
