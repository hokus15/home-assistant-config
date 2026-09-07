param(
    [string[]]$Version
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$configDir = Join-Path $repoRoot "config"
$tmpDir = Join-Path $repoRoot ".tmp-ha-ci"

if (-not $Version -or $Version.Count -eq 0) {
    $installedVersion = (Get-Content -Raw (Join-Path $configDir ".HA_VERSION")).Trim()
    $Version = @($installedVersion, "stable")
}

if (Test-Path $tmpDir) {
    $resolvedTmp = (Resolve-Path $tmpDir).Path
    if (-not $resolvedTmp.StartsWith($repoRoot.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove temp directory outside repo: $resolvedTmp"
    }
    Remove-Item -LiteralPath $resolvedTmp -Recurse -Force
}

New-Item -ItemType Directory -Force -Path (Join-Path $tmpDir "config") | Out-Null

Push-Location $repoRoot
try {
    $configFiles = git ls-files --cached --others --exclude-standard config
    foreach ($file in $configFiles) {
        $destination = Join-Path $tmpDir $file
        New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
        Copy-Item -LiteralPath (Join-Path $repoRoot $file) -Destination $destination -Force
    }

    Copy-Item `
        -LiteralPath (Join-Path $tmpDir "config\secrets.fake.yaml") `
        -Destination (Join-Path $tmpDir "config\secrets.yaml") `
        -Force

    New-Item -ItemType Directory -Force -Path (Join-Path $tmpDir "config\camera") | Out-Null

    $configuration = Join-Path $tmpDir "config\configuration.yaml"
    $seguridad = Join-Path $tmpDir "config\packages\seguridad.yaml"

    (Get-Content -Raw $configuration) `
        -replace "/share/camera", "./config/camera" `
        -replace "/media/camera", "./config/camera" `
        -replace "/media/aqara_video", "./config/camera" |
        Set-Content -NoNewline $configuration

    (Get-Content -Raw $seguridad) `
        -replace "/share/camera", "./config/camera" |
        Set-Content -NoNewline $seguridad

    foreach ($item in $Version) {
        $image = "ghcr.io/home-assistant/home-assistant:$item"
        Write-Host "Checking Home Assistant configuration with $image"

        docker run --rm `
            -v "${tmpDir}:/github/workspace" `
            --workdir /github/workspace `
            $image `
            python -m homeassistant --config ./config --script check_config
        if ($LASTEXITCODE -ne 0) {
            throw "Home Assistant configuration check failed for $item (exit $LASTEXITCODE)."
        }
    }
}
finally {
    Pop-Location
}
