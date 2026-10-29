# build-installer.ps1 - make app\build\Copyist-Setup.exe on Windows.
# Fetches WinSparkle 0.9.4 once (sha256 checked) for both x64 and ARM64,
# then runs Inno Setup 6 with the version from VERSION. Used by CI.
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path -Parent $here
$url = 'https://github.com/vslavik/winsparkle/releases/download/v0.9.4/WinSparkle-0.9.4.zip'
$sha = '6037df37fc263bd1650a1c4949681a9d40ffe991d01f35892a406cb5d103c976'
$zip = Join-Path $env:TEMP 'WinSparkle-0.9.4.zip'
if (-not (Test-Path $zip)) {
    [Net.ServicePointManager]::SecurityProtocol = 'Tls12'
    Invoke-WebRequest $url -OutFile $zip -UseBasicParsing
}
if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $sha) {
    Remove-Item $zip; throw "WinSparkle's download didn't match its checksum."
}
$x = Join-Path $env:TEMP 'WinSparkle-0.9.4'
if (-not (Test-Path $x)) { Expand-Archive $zip -DestinationPath $x }
foreach ($arch in 'x64', 'ARM64') {
    $dest = Join-Path $here "winsparkle\$arch"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item (Join-Path $x "WinSparkle-0.9.4\$arch\Release\WinSparkle.dll") $dest -Force
}
$iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) { throw 'Inno Setup 6 is not installed.' }
$version = (Get-Content (Join-Path $root 'VERSION') -Raw).Trim()
New-Item -ItemType Directory -Force (Join-Path $root 'app\build') | Out-Null
& $iscc "/DAppVersion=$version" (Join-Path $here 'Copyist.iss')
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
"built app\build\Copyist-Setup.exe ($version)"
