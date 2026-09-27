@echo off
chcp 65001 > nul
title 決算トレード - 週刊note記事自動生成ツール

echo ==========================================================
echo   📝 週刊note記事 自動生成ツール
echo   - 来週（決算約1週間前）の注目企業を東証全銘柄から自動抽出
echo   - テクニカル分析、業績進捗、100万円資金管理シナリオを生成
echo   - 記事を reports\note\ に保存し、クリップボードに自動コピー
echo ==========================================================
echo.

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

py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py -3 tools\note_generator.py
    goto end
)

python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python tools\note_generator.py
    goto end
)

echo [エラー] 有効な Python 実行環境が見つかりませんでした。
pause

:end
echo.
echo ==========================================================
echo   完了しました。noteのエディタに [Ctrl + V] で貼り付け可能です。
echo ==========================================================
pause
