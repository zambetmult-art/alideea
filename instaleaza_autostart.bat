@echo off
title Instalare ALIDEEA Autostart
echo.
echo ============================================
echo  Instalare autostart ALIDEEA...
echo ============================================
echo.

:: Sterge task vechi daca exista
schtasks /delete /tn "ALIDEEA-Watchdog" /f >nul 2>&1

:: Importa task din XML
schtasks /create /xml "C:\ALIDEEA\ALIDEEA-Watchdog.xml" /tn "ALIDEEA-Watchdog" /f
if %errorlevel% neq 0 (
    echo.
    echo EROARE la creare task! Rulati ca Administrator.
    pause
    exit /b 1
)

echo.
echo Task creat cu succes!
echo.

:: Sterge din Startup vechi ca sa nu fie conflicte
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\porneste_server.bat" >nul 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\start.bat" >nul 2>&1

echo Pornesc aplicatia acum...
echo.

:: Porneste watchdog-ul direct
start "" /min "C:\Users\zambe\AppData\Local\Programs\Python\Python313\python.exe" "C:\ALIDEEA\watchdog.py"

echo.
echo ============================================
echo  GATA! ALIDEEA va porni automat la fiecare
echo  repornire a calculatorului.
echo.
echo  Watchdog activ - repornire automata la:
echo   - Flask (app)
echo   - ngrok (acces online)
echo   - Bot Telegram
echo ============================================
echo.
timeout /t 5
