# ==============================================================================
# NEONDROP - Media Assets Restore Script (Windows PowerShell)
# ==============================================================================
param (
    [Parameter(Mandatory=$true, Position=0)]
    [string]$ArchiveFile
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $ArchiveFile)) {
    Write-Error "Media archive file not found: $ArchiveFile"
    exit 1
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " [NEONDROP] Restoring Media Assets from: $ArchiveFile" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

python manage.py restore_media "$ArchiveFile"

Write-Host "========================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Media Assets Restored Successfully!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
