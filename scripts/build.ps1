# 本地一键打包（Windows）：构建前端 -> PyInstaller -> 出 zip + SHA256
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

Write-Host "== 0/4 结束正在运行的实例 =="
Get-Process wxvideo -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

Write-Host "== 1/4 构建前端 =="
Push-Location web; npm install; npm run build; Pop-Location

Write-Host "== 2/4 准备 Python 依赖 =="
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    uv venv --python 3.12 .venv
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
}
uv pip install --python .venv\Scripts\python.exe pyinstaller

Write-Host "== 3/4 PyInstaller =="
& ".venv\Scripts\pyinstaller.exe" --noconfirm packaging\wxvideo.spec

Write-Host "== 4/4 打包 zip + SHA256 =="
$ver = (Select-String -Path "core\wxvideo_core\__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$zip = "wxvideo-$ver-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "dist\wxvideo\*" -DestinationPath $zip
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash
"$hash  $zip" | Out-File -Encoding ascii "$zip.sha256"
Write-Host "完成 -> $zip"
Write-Host "SHA256: $hash"
