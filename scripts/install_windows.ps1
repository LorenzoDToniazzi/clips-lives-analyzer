$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Has-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WingetPackage([string]$Id, [string]$Name) {
    if (-not (Has-Command "winget")) {
        throw "O $Name precisa ser instalado, mas o winget nao esta disponivel. Atualize o App Installer pela Microsoft Store e tente novamente."
    }
    Write-Host "Instalando $Name..." -ForegroundColor Cyan
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Nao foi possivel instalar $Name pelo winget."
    }
    Refresh-Path
}

function Resolve-Python311 {
    if (Has-Command "py") {
        $candidate = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return [string]($candidate | Select-Object -Last 1)
        }
    }
    if (Has-Command "python") {
        $candidate = & python -c "import sys; assert sys.version_info[:2] == (3, 11); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return [string]($candidate | Select-Object -Last 1)
        }
    }
    return $null
}

$pythonExecutable = Resolve-Python311
if (-not $pythonExecutable) {
    Install-WingetPackage "Python.Python.3.11" "Python 3.11"
    $pythonExecutable = Resolve-Python311
    if (-not $pythonExecutable) {
        throw "O Python 3.11 foi instalado, mas nao foi encontrado. Reinicie o computador e execute INSTALAR.bat novamente."
    }
}

if (-not (Has-Command "ffmpeg") -or -not (Has-Command "ffprobe")) {
    Install-WingetPackage "Gyan.FFmpeg" "FFmpeg"
}
Refresh-Path

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente isolado..." -ForegroundColor Cyan
    & $pythonExecutable -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar o ambiente Python."
    }
}

$venvPython = Join-Path $PWD.Path ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install --upgrade -e .
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao instalar o Picotador de Lives."
}

Write-Host "Validando o programa..." -ForegroundColor Cyan
& $venvPython -m compileall -q -f src tests
if ($LASTEXITCODE -ne 0) {
    throw "O codigo nao compilou."
}
& $venvPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Os testes internos falharam."
}

& ffmpeg -version | Select-Object -First 1
& ffprobe -version | Select-Object -First 1

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Picotador de Lives.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $PWD.Path "ABRIR.bat"
$shortcut.WorkingDirectory = $PWD.Path
$shortcut.Description = "Divide VODs sem perder qualidade"
$shortcut.Save()

Write-Host ""
Write-Host "Pronto. Use o atalho 'Picotador de Lives' na area de trabalho." -ForegroundColor Green
