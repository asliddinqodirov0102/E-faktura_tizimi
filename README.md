# 🧾 Elektron Hisob-Faktura Tizimi (E-Faktura API)

Kiyim-kechak do'koni uchun professional **FastAPI** asosidagi Elektron Hisob-Faktura backend tizimi.

---

## 📁 Loyiha Strukturasi

```
Elektron_hisob_faktura/
├── app/
│   ├── __init__.py
│   ├── main.py              ← FastAPI asosiy kirish nuqtasi
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        ← .env konfiguratsiyasi (Pydantic Settings)
│   │   └── database.py      ← SQLAlchemy ulanishi va SessionLocal
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/              ← Kelajakdagi API endpoint'lar
│   │       └── __init__.py
│   ├── models/              ← SQLAlchemy modellari (jadvallar)
│   │   └── __init__.py
│   └── schemas/             ← Pydantic sxemalari (validatsiya)
│       └── __init__.py
├── .env                     ← Maxfiy o'zgaruvchilar (GitHub'ga yuklanmaydi!)
├── .env.example             ← Namuna (GitHub'ga yuklanadi)
├── .gitignore
├── render.yaml              ← Render.com konfiguratsiyasi
├── requirements.txt
└── README.md
```

---

## 🚀 Lokal Ishga Tushirish

### 1. Virtual muhit yaratish
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. Kutubxonalarni o'rnatish
```bash
pip install -r requirements.txt
```

### 3. `.env` fayl yaratish
```bash
cp .env.example .env
# .env faylni ochib, haqiqiy qiymatlarni kiriting
```

### 4. Serverni ishga tushirish
```bash
# Lokal ishlab chiqish uchun (auto-reload bilan):
uvicorn app.main:app --reload --port 8000

# Production rejimida (Gunicorn + Uvicorn):
gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 5. API hujjatlarini ko'rish
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

---

## ☁️ Render.com'ga Deploy Qilish

### 1. GitHub'ga yuklash
```bash
git init
git add .
git commit -m "Initial commit: FastAPI E-Faktura tizimi"
git remote add origin https://github.com/username/elektron-hisob-faktura.git
git push -u origin main
```

### 2. Render.com sozlash
1. [render.com](https://render.com) ga kiring
2. **New → Web Service** tugmasini bosing
3. GitHub reponi tanlang
4. Quyidagi sozlamalarni kiriting:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`
5. **Environment Variables** bo'limida `DATABASE_URL` ni kiriting

### 3. PostgreSQL bazasini ulash
1. Render'da **New → PostgreSQL** yarating
2. `DATABASE_URL` ni nusxalab, Web Service'ga qo'shing

---

## 🔑 Muhit O'zgaruvchilari

| O'zgaruvchi | Tavsif | Majburiy |
|---|---|---|
| `DATABASE_URL` | PostgreSQL ulanish URL'i | ✅ Ha |
| `SECRET_KEY` | JWT token uchun maxfiy kalit | ✅ Ha |
| `ALGORITHM` | JWT algoritm (default: HS256) | Yo'q |
| `DEBUG` | Debug rejim (default: False) | Yo'q |
| `ALLOWED_ORIGINS` | CORS uchun ruxsat etilgan URL'lar | Yo'q |

---

## 📋 API Endpoint'lar

| Method | URL | Tavsif |
|---|---|---|
| GET | `/` | Ilova holati |
| GET | `/health` | Tizim va baza holati |
| GET | `/docs` | Swagger UI hujjatlari |
| GET | `/redoc` | ReDoc hujjatlari |

---

## 🛣️ Keyingi Qadamlar

- [ ] **2-QADAM**: Modellar (Mijoz, Mahsulot, Hisob-Faktura)
- [ ] **3-QADAM**: Pydantic Sxemalari (validatsiya)
- [ ] **4-QADAM**: CRUD operatsiyalari
- [ ] **5-QADAM**: API Endpoint'lar
- [ ] **6-QADAM**: JWT Autentifikatsiya
- [ ] **7-QADAM**: Alembic Migratsiyalar
