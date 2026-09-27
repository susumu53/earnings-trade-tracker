@echo off
chcp 65001 > nul
title 決算トレード予測・検証システム

echo ==========================================================
echo   決算プレトレード予測・検証ダッシュボードを起動中...
echo   ブラウザが自動的に開きます (http://localhost:8080)
echo ==========================================================

:: Pythonの実行パスを自動検出
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" main.py
    goto end
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" main.py
    goto end
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" main.py
    goto end
)

:: py ランチャーを試行
py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py -3 main.py
    goto end
)

:: システムPATHの python を試行
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python main.py
    goto end
)

echo [エラー] 有効な Python 実行環境が見つかりませんでした。
echo Python 3.9以上をインストールして実行してください。
echo https://www.python.org/downloads/

:end
pause

