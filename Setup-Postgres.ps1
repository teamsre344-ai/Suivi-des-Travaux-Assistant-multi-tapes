param(
  [string]$DbName = "crm_msui",
  [string]$DbUser = "crm_user",
  [string]$DbPassword = "StrongPassword!123",
  [string]$Hosts = "localhost",
  [int]$Port = 5432,
  [string]$PgSuperUser = "postgres",   # change if your superuser is different
  [string]$PgSuperPass = ""
)

$ErrorActionPreference = "Stop"

# 0) Check psql
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
  Write-Error "psql not found. Add PostgreSQL\bin to PATH or open 'SQL Shell (psql)'."
}

# 1) Create role & DB (idempotent)
$env:PGPASSWORD = $PgSuperPass
$createRole = "DO $$ BEGIN
IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DbUser') THEN
  CREATE ROLE $DbUser LOGIN PASSWORD '$DbPassword';
END IF;
END $$;"
$createDb = "DO $$ BEGIN
IF NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DbName') THEN
  CREATE DATABASE $DbName OWNER $DbUser;
END IF;
END $$;"

psql -h $Host -p $Port -U $PgSuperUser -d postgres -c "$createRole"
psql -h $Host -p $Port -U $PgSuperUser -d postgres -c "$createDb"
psql -h $Host -p $Port -U $PgSuperUser -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DbName TO $DbUser;"

Write-Host "✅ Postgres: role '$DbUser' and database '$DbName' ready."

# 2) Ensure driver is installed
.\.venv\Scripts\pip.exe install psycopg2-binary==2.9.9 | Out-Null

# 3) Run migrations on Postgres
$env:DB_ENGINE = "postgresql"
$env:DB_NAME = $DbName
$env:DB_USER = $DbUser
$env:DB_PASSWORD = $DbPassword
$env:DB_HOST = $Hosts
$env:DB_PORT = "$Port"

.\.venv\Scripts\python.exe manage.py migrate

Write-Host "✅ Migrations applied to Postgres."
