$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Has-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WingetPackage([string]$Id, [string]$Name) {
    Write-Host "Instalando $Name..." -ForegroundColor Cyan
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
}

if (-not (Has-Command "winget")) {
    throw "O winget não está disponível. Atualize o App Installer pela Microsoft Store."
}

$pythonCommand = $null
if (Has-Command "py") {
    try {
        & py -3.11 --version | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $pythonCommand = @("py", "-3.11")
        }
    } catch {}
}
if (-not $pythonCommand) {
    Install-WingetPackage "Python.Python.3.11" "Python 3.11"
    $pythonCommand = @("py", "-3.11")
}

if (-not (Has-Command "ffmpeg")) {
    Install-WingetPackage "Gyan.FFmpeg" "FFmpeg"
}
if (-not (Has-Command "ollama")) {
    Install-WingetPackage "Ollama.Ollama" "Ollama"
}
Refresh-Path

if (Has-Command "nvidia-smi") {
    Write-Host "GPU NVIDIA encontrada." -ForegroundColor Green
} else {
    Write-Warning "nvidia-smi não foi encontrado. Atualize o driver NVIDIA para usar a GPU."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente isolado..." -ForegroundColor Cyan
    & $pythonCommand[0] $pythonCommand[1] -m venv .venv
}
$venvPython = Join-Path $PWD ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao preparar o instalador Python."
}
& $venvPython -m pip install --upgrade -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao instalar o Clips Lives Analyzer."
}

Write-Host "Compilando e testando o programa..." -ForegroundColor Cyan
& $venvPython -m compileall -q -f src tests
if ($LASTEXITCODE -ne 0) {
    throw "O código não compilou corretamente."
}
& $venvPython -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Os testes internos falharam. Não prossiga com esta versão."
}

$ollamaReady = $false
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null
    $ollamaReady = $true
} catch {}
if (-not $ollamaReady) {
    Write-Host "Iniciando o motor local de IA..." -ForegroundColor Cyan
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null
            $ollamaReady = $true
            break
        } catch {}
    }
}
if (-not $ollamaReady) {
    throw "O Ollama foi instalado, mas não iniciou. Reinicie o Windows e rode INSTALAR.bat novamente."
}

Write-Host "Baixando o analista visual local (aprox. 6,1 GB)..." -ForegroundColor Cyan
& ollama pull qwen3-vl:8b
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao baixar qwen3-vl:8b."
}

Write-Host "Baixando o modelo de transcrição..." -ForegroundColor Cyan
& $venvPython -c "from faster_whisper import WhisperModel; WhisperModel('turbo', device='cpu', compute_type='int8'); print('Whisper pronto')"
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao preparar o Whisper."
}

Write-Host "Executando diagnóstico completo, incluindo inferência real do Whisper na GPU..." -ForegroundColor Cyan
& $venvPython -m clips_lives_analyzer doctor
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "O programa foi instalado, mas o diagnóstico obrigatório falhou." -ForegroundColor Yellow
    Write-Host "Se a falha for 'Whisper GPU', confirme CUDA 12, cuBLAS e cuDNN 9 no Windows." -ForegroundColor Yellow
    throw "Diagnóstico incompleto. Corrija o item marcado como ATENÇÃO antes de analisar VODs."
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Clips Lives Analyzer.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $PWD.Path "ABRIR.bat"
$shortcut.WorkingDirectory = $PWD.Path
$shortcut.Description = "Analisador local de VODs"
$shortcut.Save()

Write-Host ""
Write-Host "Pronto. Use o atalho 'Clips Lives Analyzer' na área de trabalho." -ForegroundColor Green
