import psycopg2

conn = psycopg2.connect('postgres://postgres:USIpIIfFC-edPvJqp5nxFsLySo8JpDp0@127.0.0.1:5433/promking')
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'videos'")
for r in cur.fetchall():
    print(r)

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
for r in cur.fetchall():
    print("Table:", r[0])
