def init_db():
    conn = get_db_connection()
    if conn is None:
        logging.error("❌ Cannot initialize DB")
        return

    try:
        cursor = conn.cursor()

        # ===== users =====
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                expire_date TIMESTAMP
            )
        """)

        # ===== history =====
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

        # ===== assistants =====
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assistants (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                owner_id BIGINT NOT NULL,
                assistant_id BIGINT NOT NULL,
                UNIQUE(chat_id, assistant_id)
            )
        """)

        # ===== Index =====
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_chat_id
            ON history(chat_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_assistants_chat_id
            ON assistants(chat_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_user_id
            ON users(user_id)
        """)

        conn.commit()
        cursor.close()
        conn.close()

        logging.info("✅ Database initialized successfully")

    except Exception as e:
        logging.error(f"❌ Database Init Error: {e}")
