@echo off
setlocal
title 週刊note記事 自動生成ツール

echo ==========================================================
echo   週刊note記事 自動生成ツール
echo ==========================================================
echo.

cd /d "%~dp0"

:: Python実行パスの自動検出
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" tools\note_generator.py
    goto end
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" tools\note_generator.py
    goto end
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" tools\note_generator.py
    goto end
)

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py -3 tools\note_generator.py
    goto end
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python tools\note_generator.py
    goto end
)

echo [エラー] 有効な Python 実行環境が見つかりませんでした。
pause
exit /b 1

:end
echo.
echo ==========================================================
echo   処理が完了しました。
echo ==========================================================
pause
