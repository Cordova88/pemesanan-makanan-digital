param([int]$Port = 8894, [switch]$Keep, [switch]$NoOrders)
# Showcase mode: the full app on a throwaway database in testing/.data/.
# Default: rebuild from scratch each run. -Keep reuses the existing showcase data.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $PSScriptRoot '.data'
Push-Location -LiteralPath $root
try {
    if (-not $Keep -and (Test-Path -LiteralPath $data)) {
        Remove-Item -LiteralPath $data -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $data | Out-Null

    python -B manage.py migrate --settings=testing.settings -v 0
    if ($LASTEXITCODE -ne 0) { throw 'migrate failed' }

    $seedArgs = @('-B', 'manage.py', 'seed_showcase', '--settings=testing.settings')
    if ($NoOrders) { $seedArgs += '--no-orders' }
    python @seedArgs
    if ($LASTEXITCODE -ne 0) { throw 'seed_showcase failed' }

    Write-Host "Customer: http://127.0.0.1:$Port/   Staff: http://127.0.0.1:$Port/staff/   Cashier: http://127.0.0.1:$Port/kasir/"
    python -B manage.py runserver "127.0.0.1:$Port" --settings=testing.settings --noreload
} finally {
    Pop-Location
}
