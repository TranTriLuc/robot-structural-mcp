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

$configPath = Join-Path $env:USERPROFILE ".claude.json"
if (-not (Test-Path $configPath)) {
    '{}' | Out-File -FilePath $configPath -Encoding utf8
}

Write-Host "==> Dang ky MCP server 'robot'..." -ForegroundColor Cyan
$json = Get-Content $configPath -Raw | ConvertFrom-Json
if (-not $json.PSObject.Properties.Name.Contains("mcpServers")) {
    $json | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{})
}
$entry = [PSCustomObject]@{
    type    = "stdio"
    command = $python
    args    = @("-m", "robot_mcp")
    env     = [PSCustomObject]@{ ROBOT_MCP_MAX_ITEMS = "200" }
}
if ($json.mcpServers.PSObject.Properties.Name -contains "robot") {
    $json.mcpServers.robot = $entry
} else {
    $json.mcpServers | Add-Member -MemberType NoteProperty -Name "robot" -Value $entry
}
$json | ConvertTo-Json -Depth 20 | Out-File -FilePath $configPath -Encoding utf8

Write-Host ""
Write-Host "Xong. Khoi dong lai Claude, mo Robot voi mot mo hinh, roi goi robot_status." -ForegroundColor Green
Write-Host "Mac dinh CHI-DOC. Muon cho phep ghi: dat ROBOT_MCP_ALLOW_WRITE=1 trong env cua MCP server." -ForegroundColor Yellow
