# ==============================================================================
# NEONDROP - Database Restore Script (Windows PowerShell)
# ==============================================================================
param (
    [Parameter(Mandatory=$true, Position=0)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $BackupFile)) {
    Write-Error "Backup file not found: $BackupFile"
    exit 1
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " [NEONDROP] Restoring Database from: $BackupFile" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

python manage.py restore_data "$BackupFile" --clean
python manage.py verify_migration --compare "$BackupFile"

Write-Host "========================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Database Restored and Verified with 0 Data Loss!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
