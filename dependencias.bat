@echo off
setlocal
cd /d "%~dp0"

where winget >nul 2>&1
if errorlevel 1 (
    echo Erro: o WinGet nao foi encontrado. Instale o App Installer da Microsoft Store e tente novamente.
    pause
    exit /b 1
)

echo Instalando Python 3.13 pelo WinGet...
winget install --id Python.Python.3.13 --exact --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo Erro ao instalar o Python 3.13.
    pause
    exit /b 1
)

echo Aguardando 1 minuto para o Python ficar disponivel...
timeout /t 60 /nobreak >nul

py -3.13 --version >nul 2>&1
if errorlevel 1 (
    echo Erro: o Python 3.13 nao foi encontrado pelo iniciador py.
    pause
    exit /b 1
)

echo Instalando dependencias do requirements.txt...
py -3.13 -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Erro ao instalar as dependencias.
    pause
    exit /b 1
)

echo Iniciando o projeto...
call "%~dp0start.bat"
if errorlevel 1 (
    echo Erro ao iniciar o start.bat.
    pause
    exit /b 1
)

endlocal