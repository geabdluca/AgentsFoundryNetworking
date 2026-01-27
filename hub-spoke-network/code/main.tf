terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}

data "azurerm_client_config" "current" {}

locals {
  resource_suffix = random_id.suffix.hex
  rg_name         = "${var.resource_group_name}-${local.resource_suffix}"
  hub_vnet_name   = "vnet-hub-${local.resource_suffix}"
  spoke_vnet_name = "vnet-foundry-spoke-${local.resource_suffix}"
}

resource "azurerm_resource_group" "main" {
  name     = local.rg_name
  location = var.location

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "hub-spoke-network"
    }
  )
}
