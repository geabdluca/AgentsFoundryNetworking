# ============================================
# DNS Server Installation and Configuration
# ============================================
# Run this script after Terraform deployment to install and configure DNS on the DNS VM

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$false)]
    [string]$VMName
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "DNS Server Installation and Configuration" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Get values from Terraform if not provided
if (-not $ResourceGroupName) {
    Write-Host "[1/4] Getting resource group name from Terraform..." -ForegroundColor Yellow
    $ResourceGroupName = terraform output -raw resource_group_name
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to get resource group name from Terraform" -ForegroundColor Red
        exit 1
    }
    Write-Host "      Resource Group: $ResourceGroupName" -ForegroundColor Green
}

if (-not $VMName) {
    Write-Host "[2/4] Getting VM name from Terraform..." -ForegroundColor Yellow
    $VMName = terraform output -raw dns_vm_name
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to get VM name from Terraform" -ForegroundColor Red
        exit 1
    }
    Write-Host "      VM Name: $VMName" -ForegroundColor Green
}

# Step 1: Install DNS Server Role
Write-Host ""
Write-Host "[3/5] Installing DNS Server role on $VMName..." -ForegroundColor Yellow

$installResult = az vm run-command invoke `
    --resource-group $ResourceGroupName `
    --name $VMName `
    --command-id RunPowerShellScript `
    --scripts "Install-WindowsFeature -Name DNS -IncludeManagementTools"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install DNS Server role" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] DNS Server role installed successfully" -ForegroundColor Green

# Wait for DNS service to start
Write-Host ""
Write-Host "[4/5] Waiting 30 seconds for DNS service to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Step 2: Configure DNS Forwarder
Write-Host ""
Write-Host "[5/5] Configuring DNS Server..." -ForegroundColor Yellow

# Configure DNS forwarder to Azure DNS
Write-Host "  > Adding DNS forwarder to 168.63.129.16..." -ForegroundColor Cyan
$forwarderResult = az vm run-command invoke `
    --resource-group $ResourceGroupName `
    --name $VMName `
    --command-id RunPowerShellScript `
    --scripts "Add-DnsServerForwarder -IPAddress 168.63.129.16 -PassThru | Select-Object IPAddress"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to configure DNS forwarder" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] DNS forwarder configured" -ForegroundColor Green

# Create conditional forwarders for Azure DNS zones (batch 1)
Write-Host "  > Creating conditional forwarders (batch 1/2)..." -ForegroundColor Cyan
$zones1 = @('services.ai.azure.com', 'api.azureml.ms', 'notebooks.azure.net', 'blob.core.windows.net', 'file.core.windows.net', 'table.core.windows.net')
$scriptContent1 = ($zones1 | ForEach-Object { "Add-DnsServerConditionalForwarderZone -Name '$_' -MasterServers 168.63.129.16" }) -join '; '

$result1 = az vm run-command invoke `
    --resource-group $ResourceGroupName `
    --name $VMName `
    --command-id RunPowerShellScript `
    --scripts $scriptContent1

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to create conditional forwarders (batch 1)" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Created 6 conditional forwarders (batch 1)" -ForegroundColor Green

# Create conditional forwarders for Azure DNS zones (batch 2)
Write-Host "  > Creating conditional forwarders (batch 2/2)..." -ForegroundColor Cyan
$zones2 = @('queue.core.windows.net', 'cognitiveservices.azure.com', 'openai.azure.com', 'documents.azure.com', 'search.windows.net', 'vaultcore.azure.net')
$scriptContent2 = ($zones2 | ForEach-Object { "Add-DnsServerConditionalForwarderZone -Name '$_' -MasterServers 168.63.129.16" }) -join '; '

$result2 = az vm run-command invoke `
    --resource-group $ResourceGroupName `
    --name $VMName `
    --command-id RunPowerShellScript `
    --scripts $scriptContent2

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to create conditional forwarders (batch 2)" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Created 6 conditional forwarders (batch 2)" -ForegroundColor Green

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "DNS Server Installation Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[OK] DNS Server role installed" -ForegroundColor Green
Write-Host "[OK] DNS forwarder configured: 168.63.129.16" -ForegroundColor Green
Write-Host "[OK] 12 conditional forwarders created:" -ForegroundColor Green
Write-Host "  - services.ai.azure.com" -ForegroundColor White
Write-Host "  - api.azureml.ms" -ForegroundColor White
Write-Host "  - notebooks.azure.net" -ForegroundColor White
Write-Host "  - blob.core.windows.net" -ForegroundColor White
Write-Host "  - file.core.windows.net" -ForegroundColor White
Write-Host "  - table.core.windows.net" -ForegroundColor White
Write-Host "  - queue.core.windows.net" -ForegroundColor White
Write-Host "  - cognitiveservices.azure.com" -ForegroundColor White
Write-Host "  - openai.azure.com" -ForegroundColor White
Write-Host "  - documents.azure.com" -ForegroundColor White
Write-Host "  - search.windows.net" -ForegroundColor White
Write-Host "  - vaultcore.azure.net" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Ensure VPN client is installed and connected"
Write-Host "2. Test DNS resolution: nslookup api.azureml.ms 10.0.1.4"
Write-Host "3. Test private endpoint: nslookup privatelink.services.ai.azure.com 10.0.1.4"
Write-Host ""
