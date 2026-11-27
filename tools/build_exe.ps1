# Build lại dist/StoryStudio.exe và dist/StoryTranslatorPro.exe từ đầu.
#
# Phải đặt thư mục của môi trường Python lên đầu PATH: nếu không, PyInstaller có thể lấy
# tcl86t.dll/tk86t.dll của bản Anaconda gốc (khác phiên bản với thư viện Tcl của môi trường)
# và exe báo "version conflict for package Tcl" khi mở.
#
# Chạy:  powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1 [-Python <python.exe>]
param([string]$Python = "$env:USERPROFILE\anaconda3\envs\p310\python.exe")
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envDir = Split-Path -Parent $Python
$env:Path = "$envDir;$envDir\Library\bin;$envDir\Scripts;$envDir\DLLs;$env:Path"
Set-Location $root
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
foreach ($name in 'StoryStudio', 'StoryTranslatorPro') {
    Remove-Item "dist\$name.exe" -Force -ErrorAction SilentlyContinue
    & $Python -m PyInstaller --clean --noconfirm "$name.spec"
    if ($LASTEXITCODE -ne 0) { throw "Build $name thất bại" }
}
Get-ChildItem dist\*.exe | Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } }, LastWriteTime
