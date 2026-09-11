$ErrorActionPreference = "Stop"

$requirements = Join-Path $PSScriptRoot "requirements.txt"
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "requirements.txt não encontrado."
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
else {
    throw "Python não encontrado. Instale Python 3.10+ e tente novamente."
}

Write-Host ""
Write-Host "Dependências instaladas." -ForegroundColor Green
Write-Host "Use:" -ForegroundColor Cyan
Write-Host '  .\tg-upload.ps1 "C:\caminho\Season 01"'
Write-Host ""
Write-Host "No primeiro uso, o Telegram pedirá login e o programa pedirá API ID/API hash."
