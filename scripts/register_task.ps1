param(
    [string]$TaskName = 'GrainPipelineIncremental',
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')][string]$At = '20:00',
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '.env'),
    [string]$BronzeRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'data\bronze'),
    [string]$LogRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'data\logs\scheduler'),
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv-automation\Scripts\python.exe'),
    [ValidateRange(0, 12)][int]$ReviewMonths = 3,
    [switch]$PreviewOnly
)
$ErrorActionPreference = 'Stop'
if ((Get-TimeZone).Id -notin @('Central Standard Time (Mexico)', 'America/Mexico_City')) {
    throw 'La hora programada requiere que Windows utilice Ciudad de Mexico.'
}
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath -ErrorAction Stop).Path
$resolvedEnv = (Resolve-Path -LiteralPath $EnvFile -ErrorAction Stop).Path
$resolvedBronze = (Resolve-Path -LiteralPath $BronzeRoot -ErrorAction Stop).Path
$resolvedLogs = [IO.Path]::GetFullPath($LogRoot)
if ((Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) -and -not $PreviewOnly) {
    throw 'Ya existe una tarea con ese nombre; no se reemplaza automaticamente.'
}
# Solo consulta SQL y originales. Nunca inicializa el historico ni consulta APIs.
& $resolvedPython -I -X utf8 -m grain_pipeline.orchestration.state --env-file $resolvedEnv --bronze-root $resolvedBronze | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'El estado publicado no permite registrar el incremental.' }
$workingDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) 'data\automation'
New-Item -ItemType Directory -Path $workingDirectory -Force | Out-Null
$arguments = '-I -X utf8 -m grain_pipeline.orchestration.scheduled --env-file "{0}" --bronze-root "{1}" --log-root "{2}" --review-months {3}' -f $resolvedEnv, $resolvedBronze, $resolvedLogs, $ReviewMonths
$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory $workingDirectory
$scheduledAt = Get-Date $At
if ($scheduledAt -le (Get-Date)) { $scheduledAt = $scheduledAt.AddDays(1) }
$trigger = New-ScheduledTaskTrigger -Daily -At $scheduledAt
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Incremental independiente FRED/Banxico hasta Gold mediante wheel instalado. Requiere historico publicado y sesion iniciada.'
if ($PreviewOnly) {
    $task | Export-ScheduledTask
    return
}
Register-ScheduledTask -TaskName $TaskName -InputObject $task | Out-Null
$registered = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
if ($registered.Actions.Execute -ne $resolvedPython -or $registered.Actions.Arguments -ne $arguments) {
    throw 'La accion registrada no coincide con la configuracion validada.'
}
Write-Output ('Tarea registrada: {0} | diaria {1} | Ciudad de Mexico | sin credenciales guardadas en la tarea.' -f $TaskName, $At)
