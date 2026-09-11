param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "upload.py"

if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "upload.py não encontrado em $PSScriptRoot"
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $script @RemainingArgs
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $script @RemainingArgs
    exit $LASTEXITCODE
}

throw "Python não encontrado. Instale Python 3.10+ e tente novamente."
