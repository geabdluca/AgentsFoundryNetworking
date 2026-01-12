# ============================================
# DNS Virtual Machine (Windows Server)
# ============================================

# Generate SSH key for VM authentication
resource "tls_private_key" "dns_vm" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# Network Interface for DNS VM
resource "azurerm_network_interface" "dns_vm" {
  name                = "${var.dns_vm_name}-nic"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.dns.id
    private_ip_address_allocation = "Static"
    private_ip_address            = cidrhost(var.hub_dns_subnet_prefix, 4)
  }

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "dns-server"
    }
  )
}

# Windows Server VM for DNS
resource "azurerm_windows_virtual_machine" "dns" {
  name                  = "${var.dns_vm_name}-${local.resource_suffix}"
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  network_interface_ids = [azurerm_network_interface.dns_vm.id]
  size                  = var.dns_vm_size
  admin_username        = var.dns_vm_admin_username
  admin_password        = random_password.dns_vm_password.result

  os_disk {
    name                 = "${var.dns_vm_name}-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = var.dns_vm_os_disk_size_gb
  }

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2022-datacenter-azure-edition"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = merge(
    var.tags,
    {
      environment = var.environment
      purpose     = "dns-server"
    }
  )
}

# Generate random password for DNS VM
resource "random_password" "dns_vm_password" {
  length  = 20
  special = true
}

# NOTE: DNS Server installation is handled by the separate install-dns-server.ps1 script
# Run after Terraform deployment completes:
#   .\install-dns-server.ps1
#
# This approach is more reliable than CustomScriptExtension which can fail silently

# REMOVED: CustomScriptExtension for DNS installation
# The extension would attempt to install DNS during Terraform apply, but it fails silently
# and doesn't provide good error handling. Use the post-deployment script instead.

# NOTE: The following DNS zones mapping is used by the install-dns-server.ps1 script:
# - documents.azure.com (Cosmos DB)
# - search.windows.net (Cognitive Search)
# - cognitiveservices.azure.com (Cognitive Services)
# - openai.azure.com (OpenAI)
# - services.ai.azure.com (AI Services)
# - blob.core.windows.net (Blob Storage)
# - file.core.windows.net (File Storage)
# - table.core.windows.net (Table Storage)
# - queue.core.windows.net (Queue Storage)
# - vaultcore.azure.net (Key Vault)
# - api.azureml.ms (Azure ML API)
# - notebooks.azure.net (Azure ML Notebooks)
