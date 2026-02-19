import os
import psycopg2
import logging

def get_db_connection():
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logging.error("❌ DATABASE_URL not found")
            return None

        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        conn = psycopg2.connect(database_url, sslmode='require')
        return conn

    except Exception as e:
        logging.error(f"❌ Database Connection Error: {e}")
        return None


def init_db():
    conn = get_db_connection()
    if conn is None:
        logging.error("❌ Cannot initialize DB")
        return

    try:
        cursor = conn.cursor()

        # ตารางเก็บสิทธิ์ผู้ใช้
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                expire_date TIMESTAMP
            )
        """)

        # ตารางบัญชี
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                amount INTEGER NOT NULL,
                description TEXT,
                balance_after INTEGER NOT NULL,
                user_name TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        cursor.close()
        conn.close()
        logging.info("✅ Database initialized successfully")

    except Exception as e:
        logging.error(f"❌ Database Init Error: {e}")
