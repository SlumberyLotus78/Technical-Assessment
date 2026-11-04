param(
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '.env'),
    [string]$BronzeRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'data\bronze'),
    [string]$LogRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'data\logs\scheduler'),
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv-automation\Scripts\python.exe'),
    [ValidateRange(0, 12)][int]$ReviewMonths = 3,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Instala primero el wheel en el entorno de automatizacion.' }
$arguments = @('-I', '-X', 'utf8', '-m', 'grain_pipeline.orchestration.scheduled',
    '--env-file', [IO.Path]::GetFullPath($EnvFile), '--bronze-root', [IO.Path]::GetFullPath($BronzeRoot),
    '--log-root', [IO.Path]::GetFullPath($LogRoot), '--review-months', [string]$ReviewMonths)
if ($CheckOnly) { $arguments += '--check-only' }
& $PythonPath @arguments
exit $LASTEXITCODE
