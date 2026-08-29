@echo off
chcp 65001 >nul
title BotProverka
cd /d "%~dp0"

echo ================================
echo      BotProverka - Запуск
echo ================================
echo.

if not exist "venv" (
    echo [*] Создаю виртуальное окружение...
    python -m venv venv
)

call venv\Scripts\activate
echo [*] Проверяю зависимости...
pip install -r requirements.txt

echo.
echo [*] Запускаю бота...
echo.
python bot.py

pause