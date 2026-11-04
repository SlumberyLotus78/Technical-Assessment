param(
    [string]$WheelPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\grain_pipeline-1.0.0-py3-none-any.whl'),
    [string]$EnvironmentDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv-automation'),
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe')
)
$ErrorActionPreference = 'Stop'
$resolvedWheel = (Resolve-Path -LiteralPath $WheelPath -ErrorAction Stop).Path
$workerPython = Join-Path ([IO.Path]::GetFullPath($EnvironmentDirectory)) 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $workerPython -PathType Leaf)) {
    & $PythonPath -m venv $EnvironmentDirectory
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno de automatizacion.' }
}
& $workerPython -m pip install --disable-pip-version-check --force-reinstall $resolvedWheel
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar el wheel y sus dependencias.' }
& $workerPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Las dependencias instaladas no son compatibles.' }
& $workerPython -I -m grain_pipeline.orchestration.incremental --help
if ($LASTEXITCODE -ne 0) { throw 'No se puede importar el paquete instalado.' }
Write-Output 'Entorno de automatizacion instalado y comprobado.'
