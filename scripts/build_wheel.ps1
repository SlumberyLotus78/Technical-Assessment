param(
    [string]$OutputDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist'),
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe')
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'No existe el Python de desarrollo.' }
& $PythonPath -X utf8 (Join-Path $PSScriptRoot 'build_wheel.py') --output-dir $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'La construccion del wheel no termino correctamente.' }
