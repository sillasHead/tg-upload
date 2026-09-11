$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "A instalação automática do tg-upload atualmente suporta apenas Windows."
}

$repo = "sillasHead/telegram-media-upload"
$root = Join-Path $env:LOCALAPPDATA "telegram-media-upload"
$appDir = Join-Path $root "app"
$binDir = Join-Path $root "bin"
$tempDir = Join-Path $env:TEMP ("telegram-media-upload-install-" + [Guid]::NewGuid().ToString("N"))

function Ensure-Directory([string]$PathValue) {
    if (-not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        New-Item -ItemType Directory -Path $PathValue -Force | Out-Null
    }
}

try {
    Write-Host "Instalando tg-upload..." -ForegroundColor Cyan
    Ensure-Directory $tempDir

    foreach ($name in @("upload.py", "requirements.txt")) {
        $url = "https://raw.githubusercontent.com/$repo/main/$name"
        $target = Join-Path $tempDir $name
        Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing
        if (-not (Test-Path -LiteralPath $target -PathType Leaf) -or (Get-Item -LiteralPath $target).Length -eq 0) {
            throw "Falha ao baixar $name."
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m pip install -r (Join-Path $tempDir "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências Python." }
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m pip install -r (Join-Path $tempDir "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências Python." }
    }
    else {
        throw "Python não encontrado. Instale Python 3.10+ e tente novamente."
    }

    if (Test-Path -LiteralPath $appDir) {
        Remove-Item -LiteralPath $appDir -Recurse -Force
    }
    Ensure-Directory $appDir
    Ensure-Directory $binDir

    Copy-Item -LiteralPath (Join-Path $tempDir "upload.py") -Destination (Join-Path $appDir "upload.py") -Force
    Copy-Item -LiteralPath (Join-Path $tempDir "requirements.txt") -Destination (Join-Path $appDir "requirements.txt") -Force

    $cmdPath = Join-Path $binDir "tg-upload.cmd"
    $cmd = @'
@echo off
setlocal
set "TG_UPLOAD_APP=%LOCALAPPDATA%\telegram-media-upload\app\upload.py"

if /I "%~1"=="update" goto update

where py >nul 2>nul
if not errorlevel 1 goto run_py

where python >nul 2>nul
if not errorlevel 1 goto run_python

echo Python nao encontrado. Instale Python 3.10+ e tente novamente.
exit /b 1

:run_py
py -3 "%TG_UPLOAD_APP%" %*
exit /b %ERRORLEVEL%

:run_python
python "%TG_UPLOAD_APP%" %*
exit /b %ERRORLEVEL%

:update
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/sillasHead/telegram-media-upload/main/setup.ps1 ^| iex"
exit /b %ERRORLEVEL%
'@
    Set-Content -LiteralPath $cmdPath -Value $cmd -Encoding ASCII

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
        $parts = @($userPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }

    if ($parts -notcontains $binDir) {
        [Environment]::SetEnvironmentVariable("Path", ((@($parts) + @($binDir)) -join ';'), "User")
    }

    if (($env:PATH -split ';') -notcontains $binDir) {
        $env:PATH = "$binDir;$env:PATH"
    }

    Write-Host ""
    Write-Host "tg-upload instalado." -ForegroundColor Green
    Write-Host "Credenciais, sessão e histórico ficam apenas em %USERPROFILE%\.telegram-media-upload."
    Write-Host ""
    Write-Host "Teste agora com:" -ForegroundColor Cyan
    Write-Host '  tg-upload "C:\caminho\Season 01" --dry-run'
    Write-Host ""
    Write-Host "Para atualizar depois:" -ForegroundColor Cyan
    Write-Host "  tg-upload update"
}
finally {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
