@echo off
cd /d "%~dp0"

start "Flask" cmd /k "py app.py"
start "Monopoli" cmd /k "py app2.py"

start "Cloudflare Tunnel" cmd /k ""%~dp0cloudflared.exe" tunnel --config "%~dp0.cloudflareD\config.yml" run"

exit