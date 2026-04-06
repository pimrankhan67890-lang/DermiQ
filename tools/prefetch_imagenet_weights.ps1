$ErrorActionPreference = "Stop"

if (!(Test-Path ".venv\\Scripts\\python.exe")) {
  throw "Missing .venv. Create it and install deps first."
}

$env:KERAS_HOME = Join-Path (Get-Location).Path ".keras_cache"
New-Item -ItemType Directory -Path $env:KERAS_HOME -Force | Out-Null

Write-Host "Prefetching MobileNetV2 ImageNet weights into: $env:KERAS_HOME" -ForegroundColor Cyan

& .\.venv\Scripts\python.exe -c @"
import os
os.environ['KERAS_HOME'] = os.environ.get('KERAS_HOME','')
import tensorflow as tf
tf.keras.applications.MobileNetV2(
    input_shape=(160,160,3),
    include_top=False,
    weights='imagenet',
    pooling='avg',
)
print('OK: weights available')
"@
