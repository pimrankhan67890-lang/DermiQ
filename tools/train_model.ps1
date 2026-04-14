param(
  [string]$Dataset = "data/train",
  [int]$Epochs = 8,
  [int]$FineTuneEpochs = 2,
  [string]$ModelOut = "models/skin_model.keras",
  [string]$LabelsOut = "models/labels.json",
  [string]$VenvDir = ".venv",
  [string]$Manifest = "data/train_manifest.jsonl",
  [switch]$Experimental
)

$ErrorActionPreference = "Stop"

Write-Host "DermIQ model training" -ForegroundColor Cyan
Write-Host "Dataset: $Dataset"

if (!(Test-Path $Dataset)) {
  throw "Dataset folder not found: $Dataset (see data/README.md)"
}

# If dataset is empty but DermNet archive has already been extracted, prepare a small dataset automatically.
$imgCount = (Get-ChildItem $Dataset -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -match '\\.(jpg|jpeg|png|bmp|webp)$' } | Measure-Object).Count
if ($imgCount -lt 10) {
  $dermnet = "data/_incoming_archive/dermnet_data/train"
  if (Test-Path $dermnet) {
    Write-Host "Dataset looks empty. Preparing a small labeled set from DermNet archive..." -ForegroundColor Yellow
    python tools/prepare_dermnet_dataset.py --dermnet-root $dermnet --out $Dataset --max-per-class 400
  }
}

Write-Host "Python:" (python --version)

if (Test-Path (Join-Path $VenvDir "Scripts\\python.exe")) {
  Write-Host "Using venv: $VenvDir" -ForegroundColor Cyan
} else {
  Write-Host "Creating venv: $VenvDir"
  python -m venv $VenvDir
}

Write-Host "Activating venv..."
& (Join-Path $VenvDir "Scripts\\Activate.ps1")

python -m pip install --upgrade pip | Out-Host
pip install -r backend/requirements.txt | Out-Host

Write-Host "Installing TensorFlow (this may take a while)..." -ForegroundColor Yellow
pip install tensorflow | Out-Host

Write-Host "Prefetching ImageNet weights (optional)..." -ForegroundColor Yellow
try {
  .\tools\prefetch_imagenet_weights.ps1 | Out-Host
} catch {
  Write-Host "Skipping ImageNet weight prefetch: $($_.Exception.Message)" -ForegroundColor DarkYellow
}

Write-Host "Building dataset manifest..." -ForegroundColor Yellow
python tools/build_dataset_manifest.py --dataset $Dataset --out $Manifest

Write-Host "Auditing dataset..." -ForegroundColor Yellow
python tools/audit_dataset.py --dataset $Dataset --manifest $Manifest $(if(-not $Experimental){'--strict'})
if ($LASTEXITCODE -ne 0) {
  throw "Dataset audit failed. Add more licensed/permitted images or rerun with -Experimental for a non-production training run."
}

Write-Host "Training..." -ForegroundColor Yellow
python train.py --dataset $Dataset --epochs $Epochs --finetune-epochs $FineTuneEpochs --out-model $ModelOut --out-labels $LabelsOut --manifest $Manifest $(if($Experimental){'--allow-small-dataset'}else{'--require-manifest-metadata'})

Write-Host "Done." -ForegroundColor Green
Write-Host "Model written to: $ModelOut"
Write-Host "Labels written to: $LabelsOut"
