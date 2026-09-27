@echo off
chcp 65001 > nul
title 決算トレード - Windowsタスクスケジューラ自動登録

echo ====================================================================
echo   ⏰ 毎週土曜日の朝9:00にnote記事を自動生成するタスクを登録します
echo ====================================================================
echo.
echo 実行ファイル: "%~dp0note記事生成_毎週土曜.bat"
echo スケジュール: 毎週土曜日 午前 09:00
echo.

schtasks /create /tn "EarningsTrade_WeeklyNote" /tr "\"%~dp0note記事生成_毎週土曜.bat\"" /sc weekly /d SAT /st 09:00 /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo ✅ 【成功】Windowsタスクスケジューラに正常登録されました！
    echo    毎週土曜日の朝9:00に自動でnote記事が生成・保存されます。
    echo.
    echo （※タスクを削除したい場合は、コマンドプロンプトで以下を実行してください）
    echo   schtasks /delete /tn "EarningsTrade_WeeklyNote" /f
) else (
    echo.
    echo ❌ 登録に失敗しました。管理者権限が必要な場合があります。
    echo    このファイルを右クリックして「管理者として実行」をお試しください。
)

echo.
pause
