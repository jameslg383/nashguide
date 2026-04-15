# NashGuide Deploy Script - Run from C:\Users\james\NashGuide
# Usage: Right-click > Run with PowerShell, or: powershell -ExecutionPolicy Bypass -File deploy.ps1

$projectDir = "C:\Users\james\NashGuide"
Set-Location $projectDir

Write-Host "=== NashGuide Deploy Script ===" -ForegroundColor Cyan

# Step 1: Create static directory
Write-Host "[1/5] Creating static directory..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "$projectDir\static" | Out-Null

# Step 2: Download landing page from the repo or check it exists
if (-not (Test-Path "$projectDir\static\index.html")) {
    Write-Host "[!] index.html not found in static folder!" -ForegroundColor Red
    Write-Host "    Save the index.html from Claude to: $projectDir\static\index.html" -ForegroundColor Red
    Write-Host "    Then run this script again." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "    index.html found!" -ForegroundColor Green

# Step 3: Update main.py to serve landing page
Write-Host "[2/5] Updating main.py..." -ForegroundColor Yellow
$mainPy = Get-Content "$projectDir\api\main.py" -Raw

# Check if FileResponse import already exists
if ($mainPy -notmatch "FileResponse") {
    # Add import
    $mainPy = $mainPy -replace "(from fastapi import FastAPI)", "`$1`nfrom fastapi.responses import FileResponse"
}

# Replace the existing root route
if ($mainPy -match '@app\.get\("/"\)\s*\nasync def root\(\):\s*\n\s*return \{') {
    $mainPy = $mainPy -replace '(?s)@app\.get\("/"\)\s*\nasync def root\(\):\s*\n\s*return \{[^}]+\}', @'
@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(static_dir / "index.html"))
'@
    Write-Host "    Root route updated!" -ForegroundColor Green
} elseif ($mainPy -match "FileResponse.*index\.html") {
    Write-Host "    Root route already serves landing page!" -ForegroundColor Green
} else {
    # Append route at the end if pattern didn't match
    $mainPy = $mainPy + @'

from fastapi.responses import FileResponse

@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(static_dir / "index.html"))
'@
    Write-Host "    Root route appended!" -ForegroundColor Green
}

Set-Content "$projectDir\api\main.py" -Value $mainPy -NoNewline

# Step 4: Git commit and push
Write-Host "[3/5] Committing changes..." -ForegroundColor Yellow
git add .
git commit -m "add landing page and serve at root"

Write-Host "[4/5] Pushing to GitHub..." -ForegroundColor Yellow
git push

# Step 5: Show server commands
Write-Host ""
Write-Host "=== PUSHED TO GITHUB ===" -ForegroundColor Green
Write-Host ""
Write-Host "Now paste these 3 lines in the Hetzner VNC console:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  cd /opt/nashguide" -ForegroundColor White
Write-Host "  git pull" -ForegroundColor White
Write-Host "  docker compose up -d --build" -ForegroundColor White
Write-Host ""
Write-Host "Then visit: http://37.27.213.238:8080" -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to exit"
