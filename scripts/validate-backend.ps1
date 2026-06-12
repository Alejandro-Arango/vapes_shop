param(
    [switch]$Production
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendPath = Join-Path $ProjectRoot "backend"
$VenvPython = Join-Path $BackendPath ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

function Invoke-Django {
    param(
        [string[]]$Arguments
    )

    & $Python @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "Fallo el comando: $Python $($Arguments -join ' ')"
    }
}

Push-Location $BackendPath

try {
    Invoke-Django @("manage.py", "check")
    Invoke-Django @("manage.py", "makemigrations", "--check", "--dry-run")
    Invoke-Django @("manage.py", "test", "store")

    if ($Production) {
        Invoke-Django @("manage.py", "check", "--deploy")
        Invoke-Django @("manage.py", "production_check")
    }
} finally {
    Pop-Location
}
