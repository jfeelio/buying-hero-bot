# Registers "BH Content Sync": runs content_sync.py every 15 minutes, hidden, as the current user.
$py   = (Get-Command python).Source -replace 'python.exe$', 'pythonw.exe'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$act  = New-ScheduledTaskAction -Execute $py -Argument "`"$here\content_sync.py`"" -WorkingDirectory $here
$trig = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$set  = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "BH Content Sync" -Action $act -Trigger $trig -Settings $set -Description "D:\Reels + D:\Posts <-> Content Tracker sheet -> GHL Instagram scheduling" -Force | Out-Null
Get-ScheduledTask -TaskName "BH Content Sync" | Select-Object TaskName, State
