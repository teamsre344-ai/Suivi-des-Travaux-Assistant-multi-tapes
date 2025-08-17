Param(
  [switch]$SkipSeed,
  [switch]$HardReset
)

$ErrorActionPreference = "Stop"
Write-Host "== CRM Upgrade ==" -ForegroundColor Cyan

# Helpers
function Py  { return ".\.venv\Scripts\python.exe" }
function Pip { return ".\.venv\Scripts\pip.exe" }

# (A) Optional hard reset (wipes DB and app migrations that may contain the bad CHECK constraint)
if ($HardReset) {
  if (Test-Path ".\db.sqlite3") { Remove-Item ".\db.sqlite3" -Force }
  Get-ChildItem ".\crm_app\migrations\*.py" `
    | Where-Object { $_.Name -ne "__init__.py" } `
    | Remove-Item -Force -ErrorAction SilentlyContinue
  Remove-Item ".\crm_app\migrations\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
  Write-Host "Hard reset complete: DB and app migrations cleared." -ForegroundColor Yellow
}

# (B) Ensure venv + deps
if (-not (Test-Path ".\.venv")) {
  python -m venv .venv
}
& (Pip) install --upgrade pip
& (Pip) install -r requirements.txt

# (C) Make sure STATIC_ROOT exists in settings so collectstatic works
$settingsPath = ".\crm_project\settings.py"
if (Test-Path $settingsPath) {
  $settings = Get-Content $settingsPath -Raw
  if ($settings -notmatch "STATIC_ROOT\s*=") {
    Add-Content $settingsPath "`n# Added by Upgrade-CRM.ps1`nSTATIC_ROOT = BASE_DIR / 'staticfiles'`n"
    Write-Host "Added STATIC_ROOT to crm_project/settings.py" -ForegroundColor Green
  }
}

# (D) Fresh migrations
& (Py) manage.py makemigrations crm_app
& (Py) manage.py migrate

# (E) Collect static (safe in dev)
if (-not (Test-Path ".\staticfiles")) { New-Item -ItemType Directory -Path ".\staticfiles" | Out-Null }
& (Py) manage.py collectstatic --noinput

# (F) Seed demo data
if (-not $SkipSeed) {
  try {
    & (Py) manage.py init_users
  } catch {
    Write-Warning "Seeding failed: $($_.Exception.Message)"
  }
}

Write-Host "`n✅ Upgrade complete." -ForegroundColor Green
