from dotenv import load_dotenv
load_dotenv()
import psycopg2, psycopg2.extras, os

conn = psycopg2.connect(
    host=os.getenv('PG_HOST'),
    port=os.getenv('PG_PORT'),
    user=os.getenv('PG_USER'),
    password=os.getenv('PG_PASSWORD'),
    dbname=os.getenv('PG_DATABASE'),
)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("""
    SELECT pid, state, wait_event_type, wait_event,
           now()-query_start AS duration,
           left(query,100) AS query
    FROM pg_stat_activity
    WHERE datname = current_database()
    ORDER BY duration DESC
    LIMIT 20
""")
for row in cur.fetchall():
    print(dict(row))