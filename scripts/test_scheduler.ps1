param(
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '.env'),
    [string]$BronzeRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'data\bronze'),
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv-automation\Scripts\python.exe'),
    [string]$ReportPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'docs\evidencias\entrega_final\scheduler_smoke.json')
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$identifier = [Guid]::NewGuid().ToString('N')
$taskName = 'GrainPipelineLearningVerification_' + $identifier
$logRoot = Join-Path $projectRoot ('data\verification\scheduler_' + $identifier)
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
$resolvedEnv = (Resolve-Path -LiteralPath $EnvFile).Path
$resolvedBronze = (Resolve-Path -LiteralPath $BronzeRoot).Path
if (Test-Path -LiteralPath $ReportPath) { throw 'El informe ya existe; elige otra ruta.' }
$arguments = '-I -X utf8 -m grain_pipeline.orchestration.scheduled --check-only --env-file "{0}" --bronze-root "{1}" --log-root "{2}"' -f $resolvedEnv, $resolvedBronze, $logRoot
$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory $projectRoot
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$created = $false
try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings | Out-Null
    $created = $true
    $started = Get-Date
    Start-ScheduledTask -TaskName $taskName
    $deadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Milliseconds 500
        $info = Get-ScheduledTaskInfo -TaskName $taskName
        $current = Get-ScheduledTask -TaskName $taskName
        $completed = $info.LastRunTime -ge $started.AddSeconds(-1) -and $current.State -ne 'Running' -and $info.LastTaskResult -ne 267009
    } while (-not $completed -and (Get-Date) -lt $deadline)
    if (-not $completed -or $info.LastTaskResult -ne 0) { throw 'El preflight desde el Programador de tareas no termino correctamente.' }
    $summary = Get-ChildItem -LiteralPath $logRoot -Filter '*.json' | Select-Object -First 1
    $result = Get-Content -LiteralPath $summary.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($result.operation -ne 'state' -or $result.exit_code -ne 0) { throw 'El resultado no corresponde a una comprobacion de solo lectura.' }
}
finally {
    if ($created) {
        if ($taskName -notmatch '^GrainPipelineLearningVerification_[0-9a-f]{32}$') { throw 'Nombre de limpieza incompatible.' }
        if ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running') { Stop-ScheduledTask -TaskName $taskName }
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}
[ordered]@{ successful = $true; scheduler_exit_code = [int]$info.LastTaskResult; operation = 'state';
    installed_wheel = $true; project_database_written = $false; api_requests_made = $false;
    temporary_verification_task_removed = $true; daily_task_replaced = $false;
    verified_at_local = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss') } | ConvertTo-Json | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Output 'Programador de tareas verificado: preflight instalado con codigo 0; tarea temporal retirada.'
