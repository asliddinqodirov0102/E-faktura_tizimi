# ============================================================
# start.ps1 — E-Faktura loyihasini ishga tushirish
# ============================================================

$Host.UI.RawUI.WindowTitle = "E-Faktura Tizimi"

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "   Elektron Hisob-Faktura Tizimi" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Virtual muhit ---
if (-not (Test-Path ".\venv")) {
    Write-Host "[1/5] Virtual muhit yaratilmoqda..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "      OK" -ForegroundColor Green
} else {
    Write-Host "[1/5] Virtual muhit mavjud." -ForegroundColor Green
}

# --- 2. Faollashtirish ---
Write-Host "[2/5] Virtual muhit faollashtirilmoqda..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"
Write-Host "      OK" -ForegroundColor Green

# --- 3. Kutubxonalar ---
$sitePackages = ".\venv\Lib\site-packages\fastapi"
if (-not (Test-Path $sitePackages)) {
    Write-Host "[3/5] Kutubxonalar o'rnatilmoqda (bir necha daqiqa)..." -ForegroundColor Yellow
    pip install -r requirements.txt --quiet
    Write-Host "      OK" -ForegroundColor Green
} else {
    Write-Host "[3/5] Kutubxonalar allaqachon o'rnatilgan." -ForegroundColor Green
}

# --- 4. PostgreSQL paroli so'rash va .env yangilash ---
Write-Host ""
Write-Host "[4/5] PostgreSQL sozlamalari..." -ForegroundColor Yellow
Write-Host ""
Write-Host "      PostgreSQL o'rnatganingizda kirgan parolingizni yozing." -ForegroundColor Cyan
Write-Host "      (Agar parol qo'ymagansiz, bo'sh qoldirib Enter bosing)" -ForegroundColor Cyan
Write-Host ""

$securePass = Read-Host "      Parol" -AsSecureString
$parol = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePass)
)

# Bo'sh parol bo'lsa — PostgreSQL trust autentifikatsiyasi uchun
if ($parol -eq "") {
    $parol = "postgres"
    Write-Host "      Bo'sh parol — 'postgres' ishlatiladi." -ForegroundColor Gray
}

# .env faylidagi DATABASE_URL ni yangilash
$envFile = ".\.env"
$envContent = Get-Content $envFile -Raw -Encoding UTF8

# Har qanday mavjud parolni yangi parol bilan almashtirish
$newDbUrl = "DATABASE_URL=postgresql://postgres:$parol@localhost:5432/efaktura_db"
$envContent = $envContent -replace "DATABASE_URL=postgresql://[^\r\n]+", $newDbUrl

Set-Content $envFile $envContent -Encoding UTF8 -NoNewline
Write-Host "      .env yangilandi: postgres:****@localhost:5432/efaktura_db" -ForegroundColor Green

# --- 5. Baza va jadvallar yaratish ---
Write-Host ""
Write-Host "[5/5] Baza va jadvallar yaratilmoqda..." -ForegroundColor Yellow

python setup_db.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Red
    Write-Host "   XATO: Baza yaratishda muammo!" -ForegroundColor Red
    Write-Host "=================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Ehtimoliy sabablar:" -ForegroundColor Yellow
    Write-Host "   1. Parol noto'g'ri — qaytadan ishga tushirib to'g'ri kiriting" -ForegroundColor White
    Write-Host "   2. PostgreSQL xizmati to'xtatilgan" -ForegroundColor White
    Write-Host "      Hal qilish: Win+R → services.msc → postgresql → Start" -ForegroundColor Gray
    Write-Host ""
    Read-Host "   Chiqish uchun Enter bosing"
    exit 1
}

# --- Server ishga tushirish ---
Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "   SERVER ISHGA TUSHDI!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Swagger (API test): http://localhost:8000/docs" -ForegroundColor White
Write-Host "   Baza holati:        http://localhost:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "   Login: admin" -ForegroundColor Green
Write-Host "   Parol: Admin@12345" -ForegroundColor Green
Write-Host ""
Write-Host "   To'xtatish: Ctrl+C" -ForegroundColor Gray
Write-Host ""

uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
