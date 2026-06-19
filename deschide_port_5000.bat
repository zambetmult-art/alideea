@echo off
powershell -Command "New-NetFirewallRule -DisplayName 'ALIDEEA Flask Port 5000' -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow -Profile Any"
echo Port 5000 deschis cu succes!
pause
