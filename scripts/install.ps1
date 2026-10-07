#Requires -Version 5.1
<#
.SYNOPSIS
  Install dsh-nexttavern (patched for a newer dsh host) into a dedicated profile.

.DESCRIPTION
  1. Patches the official npm tarball so its peerDependencies match the local dsh host.
  2. Installs it into its own profile (your existing 'web' profile is untouched).
  3. Adds a stub for @deepseek-ai/dsh-invariants (removed upstream), junction-linked
     so both the plugin and the host resolve to the same physical path.
  4. Grants the host's exact-version exemption.

.EXAMPLE
  .\install.ps1 -ProfileName tavern -Port 3096
#>
[CmdletBinding()]
param(
    [string]$ProfileName = 'tavern',
    [int]$Port = 3096,
    [string]$PluginVersion = '0.2.9',
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'

function Fail([string]$msg) { Write-Host "[x] $msg" -ForegroundColor Red; exit 1 }
function Ok([string]$msg)   { Write-Host "[ok] $msg" -ForegroundColor Green }
function Info([string]$msg) { Write-Host "     $msg" -ForegroundColor Gray }

# --- 1. Node 24+ ------------------------------------------------------------
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { Fail "node not found in PATH. dsh-nexttavern requires Node >= 24." }
$nodeVer = [version](& node -v).TrimStart('v')
if ($nodeVer.Major -lt 24) { Fail "Node $nodeVer detected, but >= 24 is required." }
Ok "Node $nodeVer"

# --- 2. dsh ----------------------------------------------------------------
$dsh = Get-Command dsh -ErrorAction SilentlyContinue
if (-not $dsh) { Fail "dsh not found in PATH." }
$dshVer = (& dsh --version).Trim()
Ok "dsh $dshVer"
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) { Fail "pnpm not found in PATH." }

$dshReal = (Get-Item $dsh.Source).Target ?? $dsh.Source
$dshRoot = Join-Path (Split-Path (Split-Path $dshReal -Parent) -Parent) '@deepseek-ai\dsh'
if (-not (Test-Path (Join-Path $dshRoot 'package.json'))) { Fail "cannot locate dsh package root" }
$hostPkgs = Join-Path $dshRoot 'node_modules\@deepseek-ai'
Ok "host root: $dshRoot"

# --- 3. Patch --------------------------------------------------------------
Write-Host "[..] patching peerDependencies (this downloads the npm tarball, ~1 min)"
$outDir = Join-Path $PSScriptRoot '..\dist'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
& python (Join-Path $PSScriptRoot 'patch.py') --plugin-version $PluginVersion --out $outDir
if ($LASTEXITCODE -ne 0) { Fail "patch.py failed" }
$tgz = Get-ChildItem -Path $outDir -Filter "*.tgz" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $tgz) { Fail "no patched tarball produced" }
Ok "patched: $($tgz.Name)"

# --- 4. Install into its own profile ---------------------------------------
Write-Host "[..] installing into profile '$ProfileName'"
& dsh plugin --profile $ProfileName add "file:///$($tgz.FullName -replace '\\','/')"
if ($LASTEXITCODE -ne 0) { Fail "plugin add failed" }
Ok "installed"

# --- 5. Make sure the profile carries the web bundle -----------------------
$profDir = Join-Path $env:USERPROFILE ".dsh\profiles\$ProfileName"
$pkgJson = Join-Path $profDir 'package.json'
if (Test-Path $pkgJson) {
    $json = Get-Content $pkgJson -Raw | ConvertFrom-Json
    $bundles = @($json.dsh.profile.bundles)
    foreach ($b in @('@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app', 'dsh-nexttavern')) {
        if ($bundles -notcontains $b) { $bundles += $b }
    }
    $json.dsh.profile.bundles = $bundles
    $json | ConvertTo-Json -Depth 8 | Set-Content $pkgJson -Encoding UTF8
    Ok "bundles: $($bundles -join ', ')"
}

# --- 6. dsh-invariants stub (host side) + junction (profile side) ----------
$stub = Join-Path $hostPkgs 'dsh-invariants'
if (-not (Test-Path $stub)) {
    New-Item -ItemType Directory -Path $stub -Force | Out-Null
    @{ name = '@deepseek-ai/dsh-invariants'; version = $dshVer; private = $true
       type = 'module'; main = 'index.js'; exports = @{ '.' = './index.js' }
       description = 'Compat stub for dsh 0.2.x; declared as a peer but never imported.' } |
        ConvertTo-Json | Set-Content (Join-Path $stub 'package.json') -Encoding UTF8
    'export {};' | Set-Content (Join-Path $stub 'index.js') -Encoding UTF8
    Ok "stub created in host"
}
$link = Join-Path $profDir "node_modules\@deepseek-ai\dsh-invariants"
if (Test-Path $link) { Remove-Item $link -Recurse -Force }
New-Item -ItemType Junction -Path $link -Target $stub | Out-Null
if ((Get-Item $link).Target -ne $stub) { Fail "junction did not resolve to the host stub" }
Ok "junction -> same physical path as host stub"

# --- 7. Exact-version exemption -------------------------------------------
foreach ($p in @('dsh-nexttavern-presets@0.3.0-dev.1')) {
    & dsh plugin --profile $ProfileName allow-version $p --dsh-version $dshVer --accept-risk
}
Ok "version exemption granted"

# --- 8. Start --------------------------------------------------------------
Write-Host ""
if ($NoStart) {
    Info "run:  dsh --profile $ProfileName --port $Port"
} else {
    Info "starting: http://127.0.0.1:$Port/  (the URL with a ?token= is printed below)"
    & dsh --profile $ProfileName --host 127.0.0.1 --port $Port
}
