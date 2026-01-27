#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Installs VPN certificates for Azure P2S VPN connection.

.DESCRIPTION
    Exports VPN certificates from Terraform and installs them to CurrentUser certificate stores.
    Run this after terraform apply to set up VPN client certificates.

.EXAMPLE
    .\install-vpn-certs.ps1
#>

$ErrorActionPreference = "Stop"

# Get the script's directory (handles running as admin which changes cwd to system32)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "`n=== VPN Certificate Installation ===" -ForegroundColor Cyan
Write-Host "Script directory: $ScriptDir" -ForegroundColor Gray
Write-Host ""

# Find OpenSSL
Write-Host "Locating OpenSSL..." -ForegroundColor Yellow
$opensslPaths = @(
    "C:\Program Files\FireDaemon OpenSSL 3\bin\openssl.exe",
    "C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
    "C:\OpenSSL-Win64\bin\openssl.exe"
)

$opensslPath = $null
foreach ($path in $opensslPaths) {
    if (Test-Path $path) {
        $opensslPath = $path
        break
    }
}

if (-not $opensslPath) {
    $found = Get-Command openssl -ErrorAction SilentlyContinue
    if ($found) {
        $opensslPath = "openssl"
    } else {
        Write-Host "[ERROR] OpenSSL not found!" -ForegroundColor Red
        Write-Host "Install with: winget install FireDaemon.OpenSSL" -ForegroundColor Yellow
        exit 1
    }
}
Write-Host "[OK] OpenSSL: $opensslPath" -ForegroundColor Green

# Step 1: Export certificates
Write-Host "`nStep 1: Exporting certificates from Terraform..." -ForegroundColor Yellow

# Determine if we're in the code folder or parent folder (use absolute paths)
$codeFolder = if (Test-Path "$ScriptDir\code\terraform.tfstate") { "$ScriptDir\code" } elseif (Test-Path "$ScriptDir\terraform.tfstate") { $ScriptDir } else { "$ScriptDir\code" }
Write-Host "Using terraform folder: $codeFolder" -ForegroundColor Gray

try {
    Push-Location $codeFolder
    # Get the raw output from Terraform
    $clientCertContent = terraform output -raw vpn_client_certificate_pem
    $clientKeyContent = terraform output -raw vpn_client_private_key_pem
    $rootCaContent = terraform output -raw vpn_root_certificate_pem
    Pop-Location
    
    # Verify we got the private key
    if (-not ($clientKeyContent -match "BEGIN.*PRIVATE KEY")) {
        throw "Invalid private key - missing BEGIN header"
    }
    
    # Function to fix PEM formatting - ensure proper line breaks
    function Fix-PemFormat {
        param([string]$PemContent)
        
        # Extract the header, body, and footer BEFORE removing whitespace
        if ($PemContent -match '(-----BEGIN[^-]+-----)(.*?)(-----END[^-]+-----)') {
            $header = $matches[1].Trim()
            $body = $matches[2] -replace '\s+', ''  # Remove whitespace only from body
            $footer = $matches[3].Trim()
            
            # Split body into 64-character lines
            $lines = @($header)
            for ($i = 0; $i -lt $body.Length; $i += 64) {
                $lines += $body.Substring($i, [Math]::Min(64, $body.Length - $i))
            }
            $lines += $footer
            
            return ($lines -join "`n")
        }
        return $PemContent
    }
    
    # Fix formatting for all certificates
    $clientCertContent = Fix-PemFormat $clientCertContent
    $clientKeyContent = Fix-PemFormat $clientKeyContent
    $rootCaContent = Fix-PemFormat $rootCaContent
    
    # Determine cert output folder (code folder) - use absolute paths
    $certFolder = if (Test-Path "$ScriptDir\code") { "$ScriptDir\code" } else { $ScriptDir }
    
    # Write with UTF8 encoding, no BOM, Unix line endings
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText("$certFolder\vpn-client-cert.pem", $clientCertContent, $utf8NoBom)
    [System.IO.File]::WriteAllText("$certFolder\vpn-client-key.pem", $clientKeyContent, $utf8NoBom)
    [System.IO.File]::WriteAllText("$certFolder\vpn-root-ca.pem", $rootCaContent, $utf8NoBom)
    
    # Debug: Show first few lines of key file
    $firstLines = (Get-Content "$certFolder\vpn-client-key.pem" -TotalCount 3)
    Write-Host "[OK] Certificates exported and formatted" -ForegroundColor Green
    Write-Host "     Key file first 3 lines:" -ForegroundColor Gray
    $firstLines | ForEach-Object { Write-Host "       $_" -ForegroundColor Gray }
} catch {
    Write-Host "[ERROR] Failed to export: $_" -ForegroundColor Red
    exit 1
}

# Determine cert folder for PFX operations (use absolute paths)
$certFolder = if (Test-Path "$ScriptDir\code") { "$ScriptDir\code" } else { $ScriptDir }

# Step 2: Create PFX
Write-Host "`nStep 2: Creating PFX with certificate chain..." -ForegroundColor Yellow
$pfxPassword = ""
$output = & $opensslPath pkcs12 -export -out "$certFolder\vpn-client.pfx" `
    -inkey "$certFolder\vpn-client-key.pem" `
    -in "$certFolder\vpn-client-cert.pem" `
    -certfile "$certFolder\vpn-root-ca.pem" `
    -password pass:$pfxPassword 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] PFX creation failed: $output" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] PFX created" -ForegroundColor Green

# Step 3: Remove old certificates
Write-Host "`nStep 3: Removing old certificates..." -ForegroundColor Yellow
Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -like "*P2S*" } | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Subject -like "*P2S*" } | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "[OK] Old certificates removed" -ForegroundColor Green

# Step 4: Install Root CA
Write-Host "`nStep 4: Installing Root CA..." -ForegroundColor Yellow
try {
    $rootCert = Import-Certificate -FilePath "$certFolder\vpn-root-ca.pem" -CertStoreLocation Cert:\CurrentUser\Root
    Write-Host "[OK] Root CA installed" -ForegroundColor Green
    Write-Host "     $($rootCert.Subject)" -ForegroundColor Gray
} catch {
    Write-Host "[ERROR] Root CA install failed: $_" -ForegroundColor Red
    exit 1
}

# Step 5: Install Client Certificate
Write-Host "`nStep 5: Installing Client certificate..." -ForegroundColor Yellow
try {
    # Use a secure string with empty password
    $securePassword = New-Object System.Security.SecureString
    $clientCert = Import-PfxCertificate -FilePath "$certFolder\vpn-client.pfx" `
        -CertStoreLocation Cert:\CurrentUser\My `
        -Password $securePassword `
        -Exportable
    Write-Host "[OK] Client certificate installed" -ForegroundColor Green
    Write-Host "     $($clientCert.Subject)" -ForegroundColor Gray
} catch {
    Write-Host "[ERROR] Client cert install failed: $_" -ForegroundColor Red
    exit 1
}

# Step 6: Verify
Write-Host "`nStep 6: Verifying..." -ForegroundColor Yellow
if ($clientCert.HasPrivateKey) {
    Write-Host "[OK] Private key present" -ForegroundColor Green
    Write-Host ""
    Write-Host "SUCCESS! VPN certificates installed." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next:" -ForegroundColor Cyan
    Write-Host "1. Install VPN client: VpnClient\WindowsAmd64\VpnClientSetupAmd64.exe" -ForegroundColor Gray
    Write-Host "2. Connect to VPN" -ForegroundColor Gray
} else {
    Write-Host "[ERROR] Private key missing!" -ForegroundColor Red
    exit 1
}
