param([int]$Port = 8890)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    python -B manage.py runserver "127.0.0.1:$Port" --settings=v1_settings --noreload
} finally {
    Pop-Location
}
