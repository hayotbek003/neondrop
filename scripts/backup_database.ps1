# ==============================================================================
# NEONDROP - Database Backup Script (Windows PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = "backups\database"

if (!(Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " [NEONDROP] Starting Automated Database Backup..." -ForegroundColor Cyan
Write-Host " Timestamp: $Timestamp" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$OutputFile = "$BackupDir\neondrop_db_$Timestamp.json"
python manage.py backup_data --output $OutputFile

Write-Host "========================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Database Backup Completed Successfully!" -ForegroundColor Green
Write-Host " Location: $OutputFile" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
