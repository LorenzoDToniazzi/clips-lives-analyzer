param(
    [string]$OutputRoot = "build\portable"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Resolve-RealTool([string]$Name) {
    $command = Get-Command $Name -ErrorAction Stop
    $candidates = @($command.Source)
    if ($env:ChocolateyInstall) {
        $packageRoot = Join-Path $env:ChocolateyInstall "lib"
        if (Test-Path $packageRoot) {
            $candidates += Get-ChildItem $packageRoot -Recurse -Filter "$Name.exe" -File |
                Select-Object -ExpandProperty FullName
        }
    }
    foreach ($candidate in $candidates) {
        $file = Get-Item $candidate -ErrorAction SilentlyContinue
        if ($file -and $file.Length -gt 1MB) {
            return $file.FullName
        }
    }
    throw "Não foi encontrado um binário real de $Name para empacotar."
}

$ffmpeg = Resolve-RealTool "ffmpeg"
$ffprobe = Resolve-RealTool "ffprobe"
$outputRootPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $OutputRoot))
$workPath = Join-Path $outputRootPath "pyinstaller-work"
$specPath = Join-Path $outputRootPath "spec"
$distPath = Join-Path $outputRootPath "dist"
$appPath = Join-Path $distPath "Picotador de Lives"
$zipPath = Join-Path $outputRootPath "Picotador-de-Lives-portatil.zip"

New-Item -ItemType Directory -Force -Path $outputRootPath | Out-Null

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --contents-directory "." `
    --name "Picotador de Lives" `
    --paths "src" `
    --workpath $workPath `
    --specpath $specPath `
    --distpath $distPath `
    --add-binary "$ffmpeg;." `
    --add-binary "$ffprobe;." `
    "src\live_splitter\__main__.py"

if ($LASTEXITCODE -ne 0) {
    throw "O PyInstaller não conseguiu gerar o executável."
}

Copy-Item "LEIA-ME-PORTATIL.txt" (Join-Path $appPath "LEIA-ME.txt") -Force

$noticePath = Join-Path $appPath "FFMPEG-LICENCA.txt"
@(
    "FFmpeg incluído como programa separado, sem alterações."
    "Projeto e código-fonte: https://ffmpeg.org/"
    "Informações e licença reportadas pelo binário distribuído:"
    ""
) | Set-Content -Path $noticePath -Encoding UTF8
& $ffmpeg -L | Add-Content -Path $noticePath -Encoding UTF8

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path (Join-Path $appPath "*") -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host "Pacote portátil criado em $zipPath" -ForegroundColor Green
