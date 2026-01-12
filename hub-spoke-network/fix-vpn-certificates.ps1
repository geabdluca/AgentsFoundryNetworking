#Requires -Version 5.1
<#
.SYNOPSIS
    Fixes VPN Error 798 by properly installing certificates to CurrentUser stores.

.DESCRIPTION
    This script addresses the common "certificate not found" (Error 798) issue with Azure VPN clients.
    
    The Windows VPN client requires certificates in the CURRENT USER stores, not LocalMachine stores.
    This script:
    1. Cleans up old VPN certificates from previous deployments
    2. Removes old VPN client profiles
    3. Installs Root CA to CurrentUser\Root
    4. Installs Client certificate with private key to CurrentUser\My
    5. Verifies proper installation

.NOTES
    - Requires OpenSSL to be installed: winget install FireDaemon.OpenSSL
    - Must be run from the hub-spoke-network directory
    - Terraform outputs must be available (cert.pem, key.pem, rootca.pem)
    - Script requires elevated permissions for some operations

.EXAMPLE
    # Export certificates and run fix script
    terraform output -raw vpn_client_certificate_pem > cert.pem
    terraform output -raw vpn_client_private_key_pem > key.pem
    terraform output -raw vpn_root_certificate_pem > rootca.pem
    .\fix-vpn-certificates.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please right-click PowerShell and select 'Run as Administrator', then run:" -ForegroundColor Yellow
    Write-Host "  cd `"$PSScriptRoot`"" -ForegroundColor Cyan
    Write-Host "  .\fix-vpn-certificates.ps1" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# Colors for output
function Write-Success { Write-Host "[OK] $args" -ForegroundColor Green }
function Write-Info { Write-Host "[INFO] $args" -ForegroundColor Cyan }
function Write-Warning { Write-Host "[WARN] $args" -ForegroundColor Yellow }
function Write-Error-Message { Write-Host "[ERROR] $args" -ForegroundColor Red }

Write-Host "`n=== VPN Certificate Fix for Error 798 ===" -ForegroundColor Cyan
Write-Host "This script installs certificates to CurrentUser stores (not LocalMachine)`n"

# Check prerequisites
Write-Info "Checking prerequisites..."

# Check for OpenSSL
try {
    $null = Get-Command openssl -ErrorAction Stop
    Write-Success "OpenSSL found"
} catch {
    Write-Error-Message "OpenSSL not found"
    Write-Warning "Install OpenSSL: winget install FireDaemon.OpenSSL"
    Write-Warning "Then restart PowerShell and run this script again"
    exit 1
}

# Check for certificate files and export from Terraform if needed
Write-Info "Checking for certificate files..."
$requiredFiles = @(
    @{File = "cert.pem"; Output = "vpn_client_certificate_pem"},
    @{File = "key.pem"; Output = "vpn_client_private_key_pem"},
    @{File = "rootca.pem"; Output = "vpn_root_certificate_pem"}
)

$needsExport = $false
foreach ($item in $requiredFiles) {
    if (-not (Test-Path $item.File)) {
        $needsExport = $true
        break
    }
}

if ($needsExport) {
    Write-Info "Certificate files not found. Exporting from Terraform..."
    
    foreach ($item in $requiredFiles) {
        try {
            Write-Info "  Exporting $($item.File)..."
            $content = terraform output -raw $item.Output 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Terraform output failed for $($item.Output)"
            }
            Set-Content -Path $item.File -Value $content -NoNewline
        } catch {
            Write-Error-Message "Failed to export $($item.File): $_"
            Write-Warning "Make sure you're in the Terraform directory and deployment is complete"
            exit 1
        }
    }
    Write-Success "All certificates exported from Terraform"
} else {
    Write-Success "All certificate files found"
}

# Step 1: Clean up old certificates
Write-Info "`nStep 1: Cleaning up old VPN certificates..."

# Remove old VPN client certificates from CurrentUser\My
$oldClientCerts = Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.Subject -like "*vpn-client*" -or 
    $_.Subject -like "*P2SClientCert*" -or
    $_.Issuer -like "*vpn-root-ca*"
}
if ($oldClientCerts) {
    Write-Info "Found $($oldClientCerts.Count) old client certificate(s) in CurrentUser\My"
    foreach ($cert in $oldClientCerts) {
        Write-Info "  Removing: $($cert.Subject) (Thumbprint: $($cert.Thumbprint))"
        $cert | Remove-Item -Force
    }
    Write-Success "Removed old client certificates from CurrentUser\My"
} else {
    Write-Info "No old client certificates found in CurrentUser\My"
}

# Remove old root CAs from CurrentUser\Root
$oldRootCerts = Get-ChildItem Cert:\CurrentUser\Root | Where-Object {
    $_.Subject -like "*vpn-root-ca*" -or 
    $_.Subject -like "*P2SRootCert*"
}
if ($oldRootCerts) {
    Write-Info "Found $($oldRootCerts.Count) old root CA(s) in CurrentUser\Root"
    foreach ($cert in $oldRootCerts) {
        Write-Info "  Removing: $($cert.Subject) (Thumbprint: $($cert.Thumbprint))"
        $cert | Remove-Item -Force
    }
    Write-Success "Removed old root CAs from CurrentUser\Root"
} else {
    Write-Info "No old root CAs found in CurrentUser\Root"
}

# Step 3: Convert and install Root CA
Write-Info "`nStep 3: Installing Root CA to CurrentUser\Root..."

# Function to format PEM content with proper line breaks
function Format-PemContent {
    param([string]$Content, [string]$BeginMarker, [string]$EndMarker)
    
    $pattern = "-----BEGIN $BeginMarker-----(.*?)-----END $EndMarker-----"
    if ($Content -match $pattern) {
        $base64Content = $matches[1] -replace '\s', ''
        
        $formattedLines = @()
        $formattedLines += "-----BEGIN $BeginMarker-----"
        for ($i = 0; $i -lt $base64Content.Length; $i += 64) {
            $length = [Math]::Min(64, $base64Content.Length - $i)
            $formattedLines += $base64Content.Substring($i, $length)
        }
        $formattedLines += "-----END $EndMarker-----"
        
        return $formattedLines -join "`n"
    }
    return $Content
}

# Validate and format root certificate file
$rootCaContent = Get-Content rootca.pem -Raw
Write-Info "Root CA file size: $($rootCaContent.Length) bytes"

if ([string]::IsNullOrWhiteSpace($rootCaContent)) {
    Write-Error-Message "rootca.pem is empty"
    exit 1
}

if ($rootCaContent -notmatch "BEGIN CERTIFICATE") {
    Write-Error-Message "rootca.pem does not contain a valid certificate"
    exit 1
}

# Format certificate with proper line breaks
$rootCaContent = Format-PemContent -Content $rootCaContent -BeginMarker "CERTIFICATE" -EndMarker "CERTIFICATE"
[System.IO.File]::WriteAllText("$PWD\rootca.pem", $rootCaContent, [System.Text.UTF8Encoding]::new($false))
Write-Info "Reformatted certificate with proper line breaks"

# Convert PEM to DER format for Windows
$rootDerFile = "rootca.der"
try {
    Write-Info "Running: openssl x509 -in rootca.pem -outform DER -out $rootDerFile"
    $opensslOutput = & openssl x509 -in rootca.pem -outform DER -out $rootDerFile 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Message "OpenSSL conversion failed with exit code: $LASTEXITCODE"
        Write-Info "OpenSSL output: $($opensslOutput | Out-String)"
        throw "OpenSSL conversion failed"
    }
    Write-Info "Converted Root CA to DER format"
} catch {
    Write-Error-Message "Failed to convert Root CA: $_"
    exit 1
}

# Import Root CA to CurrentUser\Root
try {
    $rootCert = Import-Certificate -FilePath $rootDerFile -CertStoreLocation Cert:\CurrentUser\Root
    Write-Success "Root CA installed to CurrentUser\Root"
    Write-Info "  Subject: $($rootCert.Subject)"
    Write-Info "  Thumbprint: $($rootCert.Thumbprint)"
    Write-Info "  Expires: $($rootCert.NotAfter.ToString('yyyy-MM-dd'))"
} catch {
    Write-Error-Message "Failed to import Root CA: $_"
    exit 1
}

# Step 4: Convert and install Client Certificate with Private Key
Write-Info "`nStep 4: Installing Client Certificate to CurrentUser\My..."

# Function to format PEM content with proper line breaks
function Format-PemContent {
    param([string]$Content, [string]$BeginMarker, [string]$EndMarker)
    
    $pattern = "-----BEGIN $BeginMarker-----(.*?)-----END $EndMarker-----"
    if ($Content -match $pattern) {
        $base64Content = $matches[1] -replace '\s', ''
        
        $formattedLines = @()
        $formattedLines += "-----BEGIN $BeginMarker-----"
        for ($i = 0; $i -lt $base64Content.Length; $i += 64) {
            $length = [Math]::Min(64, $base64Content.Length - $i)
            $formattedLines += $base64Content.Substring($i, $length)
        }
        $formattedLines += "-----END $EndMarker-----"
        
        return $formattedLines -join "`n"
    }
    return $Content
}

# Format client certificate
$certContent = Get-Content cert.pem -Raw
$certContent = Format-PemContent -Content $certContent -BeginMarker "CERTIFICATE" -EndMarker "CERTIFICATE"
[System.IO.File]::WriteAllText("$PWD\cert.pem", $certContent, [System.Text.UTF8Encoding]::new($false))
Write-Info "Reformatted client certificate"

# Format private key - detect key type
$keyContent = Get-Content key.pem -Raw
if ($keyContent -match "-----BEGIN (.+?)-----") {
    $keyType = $matches[1]
    $keyContent = Format-PemContent -Content $keyContent -BeginMarker $keyType -EndMarker $keyType
    [System.IO.File]::WriteAllText("$PWD\key.pem", $keyContent, [System.Text.UTF8Encoding]::new($false))
    Write-Info "Reformatted private key ($keyType)"
} else {
    Write-Error-Message "Could not detect private key type"
    exit 1
}

# Convert to PKCS#12 (.pfx) format with private key
$pfxFile = "client.pfx"
$pfxPassword = "TempP@ssw0rd123!"  # Temporary password for PFX
try {
    $opensslOutput = & openssl pkcs12 -export -out $pfxFile `
        -inkey key.pem `
        -in cert.pem `
        -certfile rootca.pem `
        -password "pass:$pfxPassword" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Message "OpenSSL PKCS#12 conversion failed with exit code: $LASTEXITCODE"
        Write-Info "OpenSSL output: $opensslOutput"
        throw "OpenSSL PKCS#12 conversion failed"
    }
    Write-Info "Converted Client Certificate to PFX format with private key"
} catch {
    Write-Error-Message "Failed to convert Client Certificate: $_"
    # Clean up temporary files
    Remove-Item $rootDerFile -Force -ErrorAction SilentlyContinue
    exit 1
}

# Import PFX to CurrentUser\My
try {
    $securePassword = ConvertTo-SecureString -String $pfxPassword -Force -AsPlainText
    $clientCert = Import-PfxCertificate -FilePath $pfxFile -CertStoreLocation Cert:\CurrentUser\My -Password $securePassword
    Write-Success "Client Certificate installed to CurrentUser\My"
    Write-Info "  Subject: $($clientCert.Subject)"
    Write-Info "  Thumbprint: $($clientCert.Thumbprint)"
    Write-Info "  Expires: $($clientCert.NotAfter.ToString('yyyy-MM-dd'))"
    Write-Info "  Has Private Key: $($clientCert.HasPrivateKey)"
    
    if (-not $clientCert.HasPrivateKey) {
        Write-Warning "Certificate imported but private key is missing!"
        Write-Warning "VPN connection may still fail"
    }
} catch {
    Write-Error-Message "Failed to import Client Certificate: $_"
    # Clean up temporary files
    Remove-Item $rootDerFile, $pfxFile -Force -ErrorAction SilentlyContinue
    exit 1
}

# Step 5: Clean up temporary files
Write-Info "`nStep 5: Cleaning up temporary files..."
Remove-Item $rootDerFile, $pfxFile -Force -ErrorAction SilentlyContinue
Write-Success "Temporary files removed"

# Step 6: Verification
Write-Info "`nStep 6: Verifying installation..."

$installedClientCert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Thumbprint -eq $clientCert.Thumbprint }
$installedRootCert = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $rootCert.Thumbprint }

if ($installedClientCert -and $installedRootCert) {
    Write-Success "Both certificates verified in CurrentUser stores"
} else {
    Write-Error-Message "Certificate verification failed!"
    if (-not $installedClientCert) { Write-Error-Message "  Client certificate not found in CurrentUser\My" }
    if (-not $installedRootCert) { Write-Error-Message "  Root CA not found in CurrentUser\Root" }
    exit 1
}

# Final check: Verify private key is accessible
if ($installedClientCert.HasPrivateKey) {
    Write-Success "Client certificate has accessible private key"
} else {
    Write-Error-Message "Client certificate private key is not accessible!"
    Write-Warning "VPN connection will fail with Error 798"
    exit 1
}

# Step 7: Get expected thumbprints from Terraform
Write-Info "`nStep 7: Comparing with Terraform outputs..."
try {
    $expectedClientThumbprint = (terraform output -raw vpn_client_certificate_thumbprint 2>$null).Trim()
    $expectedRootThumbprint = (terraform output -raw vpn_root_certificate_thumbprint 2>$null).Trim()
    
    if ($expectedClientThumbprint -and $expectedRootThumbprint) {
        Write-Info "Expected Client Thumbprint: $expectedClientThumbprint"
        Write-Info "Installed Client Thumbprint: $($clientCert.Thumbprint)"
        Write-Info "Expected Root Thumbprint: $expectedRootThumbprint"
        Write-Info "Installed Root Thumbprint: $($rootCert.Thumbprint)"
        
        if ($clientCert.Thumbprint -eq $expectedClientThumbprint -and $rootCert.Thumbprint -eq $expectedRootThumbprint) {
            Write-Success "Thumbprints match Terraform outputs"
        } else {
            Write-Warning "Thumbprints do not match Terraform outputs"
            Write-Warning "This may indicate certificate mismatch"
        }
    }
} catch {
    Write-Info "Could not retrieve Terraform outputs (this is optional)"
}

# Summary
Write-Host "`n=== Certificate Installation Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "[OK] Root CA installed: Cert:\CurrentUser\Root\$($rootCert.Thumbprint)" -ForegroundColor Green
Write-Host "[OK] Client Certificate installed: Cert:\CurrentUser\My\$($clientCert.Thumbprint)" -ForegroundColor Green
Write-Host "[OK] Private key accessible: $($clientCert.HasPrivateKey)" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Download VPN client from Azure Portal (if not already done)"
Write-Host "2. Install VPN client (run VpnClientSetupAmd64.exe)"
Write-Host "3. Connect to VPN (certificates will be used automatically)"
Write-Host ""
Write-Host "Note: If you still get Error 798:" -ForegroundColor Yellow
Write-Host "  - Re-download the VPN client from Azure Portal" -ForegroundColor Yellow
Write-Host "  - Ensure you're using the latest VPN client installer" -ForegroundColor Yellow
Write-Host "  - Check Windows Event Viewer for detailed error messages" -ForegroundColor Yellow
Write-Host ""
