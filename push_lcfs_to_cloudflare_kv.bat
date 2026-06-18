@echo off
setlocal

powershell -ExecutionPolicy Bypass -File "C:\Users\ehakm\Documents\ELHApp-backend\push_lcfs_to_cloudflare_kv.ps1"

echo.
pause
