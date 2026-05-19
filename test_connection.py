"""
test_connection.py
===================
PostgreSQL ulanishini turli parollar bilan sinab ko'radi.
Ishlatish: python test_connection.py
"""
import psycopg2

HOST = "localhost"
PORT = 5432
USER = "postgres"
DB   = "postgres"   # Default baza (har doim bor)

print("\n" + "="*50)
print("  PostgreSQL Ulanish Testi")
print("="*50)

# Sinab ko'riladigan keng tarqalgan parollar
parollar = ["postgres", "admin", "1234", "12345", "password", "root", ""]

topildi = False
for parol in parollar:
    try:
        conn = psycopg2.connect(
            host=HOST, port=PORT, user=USER,
            password=parol, database=DB,
            connect_timeout=3
        )
        conn.close()
        print(f"\n  ✅ PAROL TOPILDI: '{parol}'")
        print(f"\n  .env fayliga shu qatorni yozing:")
        print(f"  DATABASE_URL=postgresql://postgres:{parol}@localhost:5432/efaktura_db")
        topildi = True
        break
    except psycopg2.OperationalError:
        print(f"  ✗  '{parol}' — noto'g'ri")

if not topildi:
    print("\n  ❌ Hech qaysi oddiy parol ishlamadi.")
    print("\n  Yechim:")
    print("  1. pgAdmin oching")
    print("  2. Servers → PostgreSQL → ustiga o'ng klik → Properties")
    print("  3. Connection tab'ida parolni ko'ring")
    print("  4. YOKI quyidagi buyruq bilan parolni o'zgartiring:")
    print('     psql -U postgres -c "ALTER USER postgres PASSWORD \'yangi_parol\';"')

print()
input("  Enter bosing...")
