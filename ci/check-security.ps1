param(
    [string[]]$Version
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Version -or $Version.Count -eq 0) {
    $Version = @((Get-Content -Raw (Join-Path $repoRoot "config/.HA_VERSION")).Trim(), "stable")
}

foreach ($item in $Version) {
    $image = "ghcr.io/home-assistant/home-assistant:$item"
    Write-Host "Testing security rules and media processing with $image"
    docker run --rm -v "${repoRoot}:/repo:ro" $image `
        python -m unittest discover -s /repo/tests -p test_security.py -v
    if ($LASTEXITCODE -ne 0) {
        throw "Security rule tests failed for $item."
    }
    Write-Host "Testing security scripts in an isolated Home Assistant instance with $image"
    docker run --rm -v "${repoRoot}:/repo:ro" $image python /repo/tests/test_security_runtime.py
    if ($LASTEXITCODE -ne 0) {
        throw "Security runtime tests failed for $item."
    }
}
