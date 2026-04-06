$ErrorActionPreference = "Stop"

$model1 = Join-Path (Get-Location) "models\\skin_model.keras"
$model2 = Join-Path (Get-Location) "models\\skin_model.h5"
$labels = Join-Path (Get-Location) "models\\labels.json"

Write-Host "DermIQ model check" -ForegroundColor Cyan
Write-Host "Python:" (python --version)

Write-Host "labels.json:" -NoNewline
if (Test-Path $labels) { Write-Host " OK ($labels)" -ForegroundColor Green } else { Write-Host " MISSING" -ForegroundColor Red }

Write-Host "skin_model.keras:" -NoNewline
if (Test-Path $model1) { Write-Host " OK ($model1)" -ForegroundColor Green } else { Write-Host " MISSING" -ForegroundColor Yellow }

Write-Host "skin_model.h5:" -NoNewline
if (Test-Path $model2) { Write-Host " OK ($model2)" -ForegroundColor Green } else { Write-Host " MISSING" -ForegroundColor Yellow }

if (!(Test-Path $model1) -and !(Test-Path $model2)) {
  Write-Host ""
  Write-Host "No trained model found. The app will use the heuristic fallback (low accuracy)." -ForegroundColor Yellow
  Write-Host "To train: see data/README.md and run tools/train_model.ps1" -ForegroundColor Yellow
}

