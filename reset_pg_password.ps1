# ============================================================
# reset_pg_password.ps1
# PostgreSQL parolini avtomatik tiklash (Administrator kerak)
# Ishlatish: PowerShell'ni Administrator sifatida oching, keyin:
#   .\reset_pg_password.ps1
# ============================================================

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  PostgreSQL Parolini Tiklash" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# --- 1. PostgreSQL service nomini topish ---
Write-Host "`n[1/5] PostgreSQL xizmati qidirilmoqda..." -ForegroundColor Yellow

$pgService = Get-Service | Where-Object { $_.Name -like "postgresql*" } | Select-Object -First 1
if (-not $pgService) {
    Write-Host "  XATO: PostgreSQL xizmati topilmadi!" -ForegroundColor Red
    Read-Host "Enter"; exit 1
}
Write-Host "  Topildi: $($pgService.Name)" -ForegroundColor Green

# --- 2. PostgreSQL data papkasini topish ---
Write-Host "`n[2/5] PostgreSQL data papkasi qidirilmoqda..." -ForegroundColor Yellow

$pgDataDir = $null

# Registry'dan topish
$regPaths = @(
    "HKLM:\SOFTWARE\PostgreSQL\Installations",
    "HKLM:\SOFTWARE\PostgreSQL Global Development Group\PostgreSQL"
)
foreach ($reg in $regPaths) {
    if (Test-Path $reg) {
        $subkeys = Get-ChildItem $reg -ErrorAction SilentlyContinue
        foreach ($key in $subkeys) {
            $dataDir = (Get-ItemProperty $key.PSPath -ErrorAction SilentlyContinue).DataDirectory
            if ($dataDir -and (Test-Path $dataDir)) {
                $pgDataDir = $dataDir
                break
            }
        }
    }
    if ($pgDataDir) { break }
}

# Keng tarqalgan joylarda qidirish
if (-not $pgDataDir) {
    $commonPaths = @(
        "C:\Program Files\PostgreSQL\17\data",
        "C:\Program Files\PostgreSQL\16\data",
        "C:\Program Files\PostgreSQL\15\data",
        "C:\Program Files\PostgreSQL\14\data",
        "C:\Program Files\PostgreSQL\13\data"
    )
    foreach ($p in $commonPaths) {
        if (Test-Path "$p\pg_hba.conf") {
            $pgDataDir = $p
            break
        }
    }
}

if (-not $pgDataDir) {
    Write-Host "  XATO: data papkasi topilmadi!" -ForegroundColor Red
    Write-Host "  Qo'lda ko'rsating (masalan: C:\Program Files\PostgreSQL\17\data)" -ForegroundColor Yellow
    $pgDataDir = Read-Host "  Data papka manzili"
}
Write-Host "  Data papka: $pgDataDir" -ForegroundColor Green

$hbaFile = "$pgDataDir\pg_hba.conf"

# --- 3. pg_hba.conf ni trust modiga o'tkazish ---
Write-Host "`n[3/5] pg_hba.conf vaqtincha o'zgartirilmoqda..." -ForegroundColor Yellow

# Zaxira nusxa
Copy-Item $hbaFile "$hbaFile.backup" -Force

# Barcha autentifikatsiyani trust ga o'tkazish
$hbaContent = Get-Content $hbaFile -Raw
$hbaContent = $hbaContent -replace "(?m)(host\s+all\s+all\s+127\.0\.0\.1/32\s+)(md5|scram-sha-256|password)", '$1trust'
$hbaContent = $hbaContent -replace "(?m)(host\s+all\s+all\s+::1/128\s+)(md5|scram-sha-256|password)", '$1trust'
$hbaContent = $hbaContent -replace "(?m)(local\s+all\s+postgres\s+)(md5|scram-sha-256|password)", '$1trust'
Set-Content $hbaFile $hbaContent -Encoding UTF8
Write-Host "  pg_hba.conf → trust modiga o'tkazildi" -ForegroundColor Green

# --- 4. PostgreSQL servisini qayta ishga tushirish ---
Write-Host "`n[4/5] PostgreSQL qayta ishga tushirilmoqda..." -ForegroundColor Yellow
Restart-Service $pgService.Name -Force
Start-Sleep -Seconds 3
Write-Host "  PostgreSQL qayta ishga tushdi" -ForegroundColor Green

# --- 5. Yangi parol o'rnatish ---
Write-Host "`n[5/5] Yangi parol o'rnatilmoqda..." -ForegroundColor Yellow

$yangiParol = "Efaktura@2024"

# psql'ni topish
$psqlExe = $null
$psqlPaths = @(
    "C:\Program Files\PostgreSQL\17\bin\psql.exe",
    "C:\Program Files\PostgreSQL\16\bin\psql.exe",
    "C:\Program Files\PostgreSQL\15\bin\psql.exe",
    "C:\Program Files\PostgreSQL\14\bin\psql.exe",
    "C:\Program Files\PostgreSQL\13\bin\psql.exe"
)
foreach ($p in $psqlPaths) {
    if (Test-Path $p) { $psqlExe = $p; break }
}

if (-not $psqlExe) {
    $psqlExe = (Get-Command psql -ErrorAction SilentlyContinue)?.Source
}

if (-not $psqlExe) {
    Write-Host "  XATO: psql topilmadi!" -ForegroundColor Red
} else {
    # Parolni o'rnatish
    $sqlCmd = "ALTER USER postgres PASSWORD '$yangiParol';"
    & $psqlExe -U postgres -h 127.0.0.1 -c $sqlCmd 2>&1 | Out-Null
    Write-Host "  Yangi parol o'rnatildi: $yangiParol" -ForegroundColor Green
}

# --- pg_hba.conf ni tiklash va xizmatni qayta ishga tushirish ---
Write-Host "`n  pg_hba.conf tiklanmoqda (md5 ga qaytish)..." -ForegroundColor Yellow
$hbaContent = Get-Content $hbaFile -Raw
$hbaContent = $hbaContent -replace "(?m)(host\s+all\s+all\s+127\.0\.0\.1/32\s+)trust", '${1}md5'
$hbaContent = $hbaContent -replace "(?m)(host\s+all\s+all\s+::1/128\s+)trust", '${1}md5'
$hbaContent = $hbaContent -replace "(?m)(local\s+all\s+postgres\s+)trust", '${1}md5'
Set-Content $hbaFile $hbaContent -Encoding UTF8

Restart-Service $pgService.Name -Force
Start-Sleep -Seconds 3
Write-Host "  PostgreSQL qayta ishga tushdi (parolli rejimda)" -ForegroundColor Green

# --- .env faylini yangilash ---
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw -Encoding UTF8
    $newDbUrl = "DATABASE_URL=postgresql://postgres:$yangiParol@localhost:5432/efaktura_db"
    $envContent = $envContent -replace "DATABASE_URL=postgresql://[^\r\n]+", $newDbUrl
    Set-Content $envFile $envContent -Encoding UTF8 -NoNewline
    Write-Host "  .env yangilandi: yangi parol yozildi" -ForegroundColor Green
}

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  MUVAFFAQIYATLI YAKUNLANDI!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  PostgreSQL yangi paroli: $yangiParol" -ForegroundColor White
Write-Host ""
Write-Host "  Endi ishga tushiring:" -ForegroundColor Yellow
Write-Host "  .\start.ps1" -ForegroundColor White
Write-Host ""
Read-Host "  Enter bosing..."
