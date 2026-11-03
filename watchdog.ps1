$proc = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*tg-api-checker*' }
if (-not $proc) { Start-ScheduledTask -TaskName 'TgApiCheckerBot' }
