# ==========================================================
# ファイル名： fix_sequences.py
# 目的： sqlite_to_postgres.py 移行時にid列を明示INSERTしたことで
#        ズレたPostgreSQLの自動採番シーケンスを、実データのMAX(id)に
#        合わせて再同期する（データは一切変更しない、1回限りのメンテ用）
# ==========================================================

from amazon.db import get_conn


def main():
    conn = get_conn("a_marketplaces_master.db")  # postgresモードではdb_name指定は無視され、単一DBに接続される
    cur = conn.cursor()

    cur.execute("""
        SELECT c.relname AS table_name, a.attname AS col_name
        FROM pg_class c
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND a.attname = 'id'
          AND pg_get_serial_sequence(c.relname, a.attname) IS NOT NULL
        ORDER BY c.relname
    """)
    targets = cur.fetchall()

    for row in targets:
        table = row["table_name"]
        cur.execute(f'SELECT COALESCE(MAX(id), 0) AS max_id FROM "{table}"')
        max_id = cur.fetchone()["max_id"]

        cur.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, %s)",
            (table, max_id if max_id > 0 else 1, max_id > 0)
        )
        print(f"[FIXED] {table}: sequence -> next value will be {max_id + 1}")

    conn.commit()
    conn.close()
    print(f"[DONE] {len(targets)} tables checked")


if __name__ == "__main__":
    main()
