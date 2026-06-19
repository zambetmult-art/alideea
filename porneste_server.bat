@echo off
title ALIDEEA Server

:: Opreste procese vechi
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im ngrok.exe >nul 2>&1
timeout /t 2 >nul

:: Porneste aplicatia Flask
start "" /min "C:\Users\zambe\AppData\Local\Programs\Python\Python313\python.exe" "C:\ALIDEEA\app.py"
timeout /t 5 >nul

:: Porneste ngrok cu domeniu fix
start "" /min "C:\ngrok\ngrok.exe" start alideea
timeout /t 3 >nul

:: Porneste botul Telegram
start "" /min "C:\Users\zambe\AppData\Local\Programs\Python\Python313\python.exe" "C:\ALIDEEA\telegram_bot.py"
timeout /t 2 >nul

:: Porneste Watchdog (reporneste automat tot ce cade)
start "" /min "C:\Users\zambe\AppData\Local\Programs\Python\Python313\python.exe" "C:\ALIDEEA\watchdog.py"

echo.
echo ================================================
echo  ALIDEEA pornit cu succes!
echo  Acces local:   http://127.0.0.1:5000
echo  Acces online:  https://backboned-brunch-letter.ngrok-free.dev
echo  Bot Telegram:  @valetu_ion_bot - ACTIV
echo  Watchdog:      ACTIV (repornire automata)
echo ================================================
echo.
timeout /t 5
