# build.ps1 - 30sec_draw.exe を生成するスクリプト
# 使い方: PowerShell で .\build.ps1 を実行

$ScriptName = "timer.py"
$AppName    = "30sec_draw"

Write-Host "=== 30sec_draw ビルドスクリプト ===" -ForegroundColor Cyan

# --- pyinstaller.exe を探す ---
$PyInstaller = $null

# 1. PATH 上にあるか確認
if (Get-Command pyinstaller -ErrorAction SilentlyContinue) {
    $PyInstaller = "pyinstaller"
}

# 2. Windows ストア版 Python のユーザー Scripts フォルダを検索
if (-not $PyInstaller) {
    $candidates = Get-ChildItem -Path "$env:LOCALAPPDATA\Packages" -Filter "pyinstaller.exe" -Recurse -ErrorAction SilentlyContinue |
                  Where-Object { $_.FullName -like "*Scripts*" } |
                  Select-Object -First 1
    if ($candidates) {
        $PyInstaller = $candidates.FullName
    }
}

# 3. python -m PyInstaller でも試みる
if (-not $PyInstaller) {
    $pyExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if ($pyExe) {
        $testResult = & $pyExe -m PyInstaller --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $PyInstaller = "$pyExe -m PyInstaller"
        }
    }
}

if (-not $PyInstaller) {
    Write-Host "[ERROR] pyinstaller が見つかりません。以下のコマンドでインストールしてください：" -ForegroundColor Red
    Write-Host "  pip install pyinstaller" -ForegroundColor Yellow
    exit 1
}

Write-Host "[INFO] pyinstaller: $PyInstaller" -ForegroundColor Green

# --- ビルド実行 ---
Write-Host "[INFO] ビルド開始..." -ForegroundColor Cyan

if ($PyInstaller -like "* -m *") {
    # python -m PyInstaller 形式
    $parts = $PyInstaller -split " -m "
    & $parts[0] -m PyInstaller --noconfirm --onefile --windowed --icon icon.ico --add-data "icon.ico;." --name $AppName $ScriptName
} else {
    & $PyInstaller --noconfirm --onefile --windowed --icon icon.ico --add-data "icon.ico;." --name $AppName $ScriptName
}

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[SUCCESS] ビルド成功！" -ForegroundColor Green
    Write-Host "  実行ファイル: dist\$AppName.exe" -ForegroundColor Green
} else {
    Write-Host "[ERROR] ビルドに失敗しました。" -ForegroundColor Red
    exit 1
}
