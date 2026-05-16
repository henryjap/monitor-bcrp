@echo off
REM Sync latest BCRP cache from GitHub Actions
gh run download -R henryjap/monitor-bcrp -n bcrp-cache-db --dir "%TEMP%\bcrp_cache"
if %ERRORLEVEL% neq 0 (
    echo ❌ Error downloading artifact. Check gh auth login
    pause
    exit /b 1
)
echo ✅ Downloaded latest cache
tar -xzf "%TEMP%\bcrp_cache\bcrp_cache_db.tar.gz" -C "%TEMP%\bcrp_cache"
copy /Y "%TEMP%\bcrp_cache\monitor_bcrp_python\data_cache\series_raw\series_cache.db" "%~dp0monitor_bcrp_python\data_cache\series_raw\series_cache.db" >nul
echo 🗄️  Cache updated in data_cache/series_raw/series_cache.db
rd /s /q "%TEMP%\bcrp_cache" 2>nul
pause