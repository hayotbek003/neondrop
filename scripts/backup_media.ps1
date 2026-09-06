# ==============================================================================
# NEONDROP - Media Assets Backup Script (Windows PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = "backups\media"

if (!(Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " [NEONDROP] Starting Media Backup..." -ForegroundColor Cyan
Write-Host " Timestamp: $Timestamp" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$OutputFile = "$BackupDir\neondrop_media_$Timestamp.tar.gz"
python manage.py backup_media --output $OutputFile

Write-Host "========================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Media Backup Completed Successfully!" -ForegroundColor Green
Write-Host " Location: $OutputFile" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
