# Cai dat robot-structural-mcp: tao venv va dang ky MCP server.
# Chay: .\install.ps1

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "Khong tim thay 'uv'. Cai tai https://docs.astral.sh/uv/ roi chay lai."
}

Write-Host "==> Tao virtualenv va cai phu thuoc..." -ForegroundColor Cyan
Push-Location $repo
uv sync
Pop-Location

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { Write-Error "Khong thay $python" }

Write-Host "==> Kiem tra server khoi dong..." -ForegroundColor Cyan
& $python -c "import robot_mcp.server; print('  OK - nap duoc module')"

# Ghi cau hinh bang Python: ~/.claude.json lon va long sau, round-trip qua
# ConvertTo-Json cua PowerShell co the lam hong cac thiet lap khong lien quan.
Write-Host "==> Dang ky MCP server 'robot'..." -ForegroundColor Cyan
& $python (Join-Path $repo "register_mcp.py")

Write-Host ""
Write-Host "Xong. Khoi dong lai Claude, mo Robot voi mot mo hinh, roi goi robot_status." -ForegroundColor Green
Write-Host "Mac dinh CHI-DOC. Muon cho phep ghi: dat ROBOT_MCP_ALLOW_WRITE=1 trong env cua MCP server." -ForegroundColor Yellow
