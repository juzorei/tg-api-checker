$bot = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*tg-api-checker*' }
if (-not $bot) { Start-ScheduledTask -TaskName 'TgApiCheckerBot' }

# Адаптер запускается как "pythonw adapter.py" без пути — проверяем по порту
$adapter = Get-NetTCPConnection -LocalPort 8320 -State Listen -ErrorAction SilentlyContinue
if (-not $adapter) { Start-ScheduledTask -TaskName 'ReplicateAdapter' }
