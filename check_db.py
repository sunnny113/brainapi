import sqlite3

conn = sqlite3.connect("brainapi.db")
cursor = conn.cursor()

print("Tables:\n")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

for t in tables:
    print(t[0])

print("\nAPI Keys:\n")

cursor.execute("SELECT * FROM api_keys")
rows = cursor.fetchall()

for r in rows:
    print(r)

conn.close()