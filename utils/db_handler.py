# utils/db_handler.py
import aiosqlite
import os
import time
import asyncio
from datetime import datetime, timezone, timedelta

# Variabel Global untuk menyimpan instance DB
_db_instance = None
_db_init_lock = asyncio.Lock()

# --- DEFINISI MIGRASI (VERSION CONTROL) ---

async def migrate_v2_weekly_chat_xp(conn):
    """Migrasi V2: Menambah kolom weekly_chat_xp."""
    # Cek dulu biar aman kalau dijalankan di DB lama yang sudah punya kolomnya
    async with conn.execute("PRAGMA table_info(weekly_stats)") as cursor:
        columns = [col[1] for col in await cursor.fetchall()]
        if 'weekly_chat_xp' not in columns:
            print("🔄 Applying Migration V2: Add weekly_chat_xp...")
            await conn.execute("ALTER TABLE weekly_stats ADD COLUMN weekly_chat_xp INTEGER DEFAULT 0")

async def migrate_v3_gamification(conn):
    """Migrasi V3: Menambah kolom untuk gamifikasi (streak, badges)."""
    async with conn.execute("PRAGMA table_info(users)") as cursor:
        columns = [col[1] for col in await cursor.fetchall()]
        
        if 'voice_streak' not in columns:
            print("🔄 Applying Migration V3: Add voice_streak...")
            await conn.execute("ALTER TABLE users ADD COLUMN voice_streak INTEGER DEFAULT 0")
        
        if 'last_voice_date' not in columns:
            print("🔄 Applying Migration V3: Add last_voice_date...")
            await conn.execute("ALTER TABLE users ADD COLUMN last_voice_date TEXT DEFAULT NULL")
            
        if 'active_title' not in columns:
            print("🔄 Applying Migration V3: Add active_title...")
            await conn.execute("ALTER TABLE users ADD COLUMN active_title TEXT DEFAULT NULL")

async def migrate_v4_global_users(conn):
    """Migrasi V4: Menambah tabel user global untuk tracking intro message."""
    print("🔄 Applying Migration V4: Create user_globals table...")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_globals (
            user_id INTEGER PRIMARY KEY,
            has_seen_jiromi_intro INTEGER DEFAULT 0,
            first_intro_at DATETIME DEFAULT NULL
        )
    """)

async def migrate_v5_chat_events(conn):
    async with conn.execute("PRAGMA table_info(users)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    if "total_chat_events" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN total_chat_events INTEGER NOT NULL DEFAULT 0")

async def migrate_v8_repair_chat_events_column(conn):
    """Repair databases whose schema version advanced without this column."""
    await migrate_v5_chat_events(conn)

async def migrate_v9_repair_weekly_recap_deliveries(conn):
    """Repair databases whose schema version advanced without recap tracking."""
    await migrate_v6_weekly_recap_deliveries(conn)

async def migrate_v6_weekly_recap_deliveries(conn):
    await conn.execute("""CREATE TABLE IF NOT EXISTS weekly_recap_deliveries (
        guild_id INTEGER NOT NULL, week_key TEXT NOT NULL, status TEXT NOT NULL,
        claimed_at REAL, posted_at REAL, attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT, PRIMARY KEY (guild_id, week_key)
    )""")
    await conn.execute("""INSERT OR IGNORE INTO weekly_recap_deliveries
        (guild_id, week_key, status, posted_at, attempts)
        SELECT guild_id, last_posted_week_key, 'posted', strftime('%s','now'), 1
        FROM weekly_config WHERE last_posted_week_key IS NOT NULL AND last_posted_week_key != ''""")

# Update Dictionary MIGRATIONS
MIGRATIONS = {
    2: migrate_v2_weekly_chat_xp,
    3: migrate_v3_gamification,
    4: migrate_v4_global_users,
    5: migrate_v5_chat_events,
    6: migrate_v6_weekly_recap_deliveries,
    8: migrate_v8_repair_chat_events_column,
    9: migrate_v9_repair_weekly_recap_deliveries,
}

async def init_db(logger=None):
    """Wrapper untuk inisialisasi database global (Thread-safe)."""
    global _db_instance
    # Pastikan hanya 1 proses yang bisa init dalam satu waktu
    async with _db_init_lock:
        if _db_instance is None:
            _db_instance = DatabaseHandler(logger=logger)
            await _db_instance.connect()
    return _db_instance

async def close_db():
    """Wrapper untuk menutup database global."""
    global _db_instance
    if _db_instance:
        await _db_instance.close()
        _db_instance = None

class DatabaseHandler:
    def __init__(self, db_path="database/schema.db", logger=None):
        self.db_path = db_path
        self._conn = None  # Single Connection
        self._write_lock = asyncio.Lock()  # Serialize Writes
        self._config_cache = {} 
        self._filter_cache = {}
        self.TTL = 60
        self.logger = logger

    def _log_db_failure(self, level, event, query, exc):
        safe_query = " ".join(str(query).split())[:500]
        if self.logger:
            self.logger.error(event, "Database operation failed", error_obj=exc, operation=safe_query)
        else:
            print(f"{event}: {exc} | {safe_query}")

    async def connect(self):
        """Membuka koneksi database persisten."""
        if not os.path.exists('database'):
            os.makedirs('database')

        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        # PRAGMA Optimization
        await self._conn.execute("PRAGMA journal_mode=WAL;") 
        await self._conn.execute("PRAGMA busy_timeout=3000;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;") 
        await self._conn.commit()

        # 1. Init Tabel Dasar (V1)
        await self._init_tables()
        
        # 2. Jalankan Migrasi (V2, V3, ...)
        # Ini akan otomatis mengecek versi dan update jika perlu
        await self._run_migrations()
   
        print("Database Connected (WAL Mode + Versioned Schema)")

    async def close(self):
        """Menutup koneksi."""
        if self._conn:
            await self._conn.close()
            print("Database Closed")

    async def _init_tables(self):
        """Membuat tabel dasar (Schema V1) & Index."""
        
        # 1. Definisi Tabel Dasar (V1)
        queries = [
            # ... (Pastikan semua query CREATE TABLE users, guild_config, dll ada di sini) ...
            # Contoh sebagian:
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER, guild_id INTEGER, xp INTEGER DEFAULT 0, 
                level INTEGER DEFAULT 0, total_voice_mins INTEGER DEFAULT 0,
                last_chat_ts REAL DEFAULT 0, PRIMARY KEY (user_id, guild_id)
            )""",
            # ... Masukkan query CREATE TABLE lainnya di sini ...
            """CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY, announce_channel_id INTEGER,
                chat_xp_val INTEGER DEFAULT 5, voice_xp_val INTEGER DEFAULT 10, 
                min_members_voice INTEGER DEFAULT 2, announcement_mode TEXT DEFAULT 'balanced'
            )""",
             """CREATE TABLE IF NOT EXISTS filters (
                guild_id INTEGER, target_id INTEGER, type TEXT, category TEXT,
                PRIMARY KEY (guild_id, target_id, category)
            )""",
            """CREATE TABLE IF NOT EXISTS rewards (
                guild_id INTEGER, level_required INTEGER, role_id INTEGER,
                PRIMARY KEY (guild_id, level_required)
            )""",
            """CREATE TABLE IF NOT EXISTS left_members (
                user_id INTEGER, guild_id INTEGER, xp INTEGER, level INTEGER, 
                total_voice_mins INTEGER, left_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            )""",
             """CREATE TABLE IF NOT EXISTS event_configs (
                guild_id INTEGER, event_type TEXT, channel_id INTEGER,
                is_enabled INTEGER DEFAULT 0, message_text TEXT, use_embed INTEGER DEFAULT 0,
                embed_title TEXT, embed_description TEXT, embed_color INTEGER DEFAULT 0,
                image_url TEXT, PRIMARY KEY (guild_id, event_type)
            )""",
            """CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)""",
             """CREATE TABLE IF NOT EXISTS weekly_stats (
                guild_id INTEGER, user_id INTEGER, week_key TEXT,                 
                weekly_xp INTEGER DEFAULT 0, weekly_voice_mins INTEGER DEFAULT 0,
                updated_at REAL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, week_key)
            )""",
             """CREATE TABLE IF NOT EXISTS weekly_config (
                guild_id INTEGER PRIMARY KEY, recap_channel_id INTEGER,
                is_enabled INTEGER DEFAULT 0, last_posted_week_key TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS user_badges (
                user_id INTEGER, guild_id INTEGER, badge_id TEXT, 
                unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id, badge_id)
            )""",
            """CREATE TABLE IF NOT EXISTS user_titles (
                user_id INTEGER, guild_id INTEGER, title_id TEXT, 
                unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id, title_id)
            )""",
            """CREATE TABLE IF NOT EXISTS user_globals (
                user_id INTEGER PRIMARY KEY,
                has_seen_jiromi_intro INTEGER DEFAULT 0,
                first_intro_at DATETIME DEFAULT NULL
            )""",
        ]

        # [cite_start]2. Definisi Index (Agar performa cepat) [cite: 38-39]
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_xp ON users(guild_id, xp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_weekly_stats_rank ON weekly_stats(guild_id, week_key, weekly_voice_mins DESC)",
            "CREATE INDEX IF NOT EXISTS idx_filters_lookup ON filters(guild_id, type)"
        ]

        # 3. Definisi Tabel Meta Versioning [PENTING]
        queries.append("""
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value INTEGER
            )
        """)

        
        # Buat Tabel
        for q in queries:
            await self._conn.execute(q)

        # Buat Index
        for idx in indexes:
            await self._conn.execute(idx)

        # Set versi awal ke 1 jika ini database baru
        await self._conn.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', 1)")
        
        # Commit perubahan struktur dasar
        await self._conn.commit()

    async def get_guild_weekly_rank(self, guild_id, week_key):
        """
        Menghitung ranking global server berdasarkan Total Voice Minutes minggu ini.
        Hanya menghitung server yang memiliki aktivitas (> 0 menit).
        Return: (rank, total_active_servers)
        """
        # 1. Ambil total voice per guild untuk minggu tertentu
        # Kita GROUP BY guild_id dan urutkan dari yang terbesar
        query = """
            SELECT guild_id, SUM(weekly_voice_mins) as total_voice
            FROM weekly_stats 
            WHERE week_key = ? 
            GROUP BY guild_id 
            HAVING total_voice > 0
            ORDER BY total_voice DESC
        """
        rows = await self.fetch_all(query, (week_key,))
        
        # 2. Cari posisi guild kita di dalam list
        rank = 0
        total_servers = len(rows)
        
        for i, row in enumerate(rows):
            if row['guild_id'] == guild_id:
                rank = i + 1  # Karena index mulai dari 0, ranking mulai dari 1
                break
                
        # Jika tidak ketemu (misal belum ada aktivitas), rank tetap 0
        return rank, total_servers

    async def execute(self, query, vars=()):
        """Execute WRITE query dengan Lock."""
        if not self._conn: 
            await self.connect() # Auto-connect safeguard
        
        try:
            async with self._write_lock: # <--- INI WAJIB ADA UNTUK WRITE
                await self._conn.execute(query, vars)
                await self._conn.commit()
        except Exception as e:
            self._log_db_failure("ERROR", "DB_WRITE_FAIL", query, e)
            raise

    async def fetch_one(self, query, vars=()):
        """Execute a read under the shared-connection lock."""
        if not self._conn: 
            await self.connect()

        try:
            async with self._write_lock:
                async with self._conn.execute(query, vars) as cursor:
                    return await cursor.fetchone()
        except Exception as e:
            self._log_db_failure("ERROR", "DB_READ_FAIL", query, e)
            raise

    async def fetch_all(self, query, vars=()):
        """Execute a read under the shared-connection lock."""
        if not self._conn: 
            await self.connect()

        try:
            async with self._write_lock:
                async with self._conn.execute(query, vars) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            self._log_db_failure("ERROR", "DB_READ_FAIL", query, e)
            raise
    # --- USER DATA & XP LOGIC ---

    async def get_user_data(self, user_id, guild_id):
        user = await self.fetch_one(
            "SELECT xp, level, total_voice_mins, last_chat_ts, total_chat_events FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
        if not user:
            # Jika user baru, buat row baru
            await self.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
            # Return dict default
            user = await self.fetch_one("SELECT xp, level, total_voice_mins, last_chat_ts, total_chat_events FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
            return dict(user)
        
        # [FIX 3] Konversi aiosqlite.Row menjadi standard Dict agar konsisten
        return dict(user)

    async def add_voice_time(self, user_id, guild_id, minutes, xp_per_min):
        total_xp_gain = minutes * xp_per_min
        async with self._write_lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._ensure_user_tx(user_id, guild_id)
                cursor = await self._conn.execute("SELECT xp, level FROM users WHERE user_id=? AND guild_id=?", (user_id, guild_id))
                row = await cursor.fetchone()
                old_level = row["level"]
                current_xp = row["xp"] + total_xp_gain
                from utils.math_utils import calculate_level
                new_level = calculate_level(current_xp)
                await self._conn.execute("UPDATE users SET xp=?, level=?, total_voice_mins=total_voice_mins+? WHERE user_id=? AND guild_id=?", (current_xp, new_level, minutes, user_id, guild_id))
                await self._upsert_weekly_stats_tx(guild_id, user_id, total_xp_gain, minutes, 0)
                await self._conn.commit()
                return {"old_level": old_level, "new_level": new_level}
            except Exception as e:
                await self._conn.rollback()
                self._log_db_failure("ERROR", "DB_WRITE_FAIL", "add_voice_time transaction", e)
                raise

    async def add_chat_xp(self, user_id, guild_id, xp_amount):
        async with self._write_lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._ensure_user_tx(user_id, guild_id)
                cursor = await self._conn.execute("SELECT xp, level FROM users WHERE user_id=? AND guild_id=?", (user_id, guild_id))
                row = await cursor.fetchone()
                old_level = row["level"]
                current_xp = row["xp"] + xp_amount
                from utils.math_utils import calculate_level
                new_level = calculate_level(current_xp)
                now = time.time()
                await self._conn.execute("UPDATE users SET xp=?, level=?, last_chat_ts=?, total_chat_events=total_chat_events+1 WHERE user_id=? AND guild_id=?", (current_xp, new_level, now, user_id, guild_id))
                await self._upsert_weekly_stats_tx(guild_id, user_id, xp_amount, 0, xp_amount)
                await self._conn.commit()
                return {"old_level": old_level, "new_level": new_level}
            except Exception as e:
                await self._conn.rollback()
                self._log_db_failure("ERROR", "DB_WRITE_FAIL", "add_chat_xp transaction", e)
                raise

    async def _ensure_user_tx(self, user_id, guild_id):
        await self._conn.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))

    async def _upsert_weekly_stats_tx(self, guild_id, user_id, xp_add, voice_mins_add, chat_xp_add):
        await self._conn.execute("""INSERT INTO weekly_stats
            (guild_id,user_id,week_key,weekly_xp,weekly_voice_mins,weekly_chat_xp,updated_at)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(guild_id,user_id,week_key) DO UPDATE SET
            weekly_xp=weekly_xp+excluded.weekly_xp,
            weekly_voice_mins=weekly_voice_mins+excluded.weekly_voice_mins,
            weekly_chat_xp=weekly_chat_xp+excluded.weekly_chat_xp,
            updated_at=excluded.updated_at""", (guild_id,user_id,self.get_current_week_key(),xp_add,voice_mins_add,chat_xp_add,time.time()))

    # --- FILTERS & CONFIG LOGIC ---

    async def get_guild_config(self, guild_id):
        # A. Cek Cache (Memory)
        if guild_id in self._config_cache:
            cache = self._config_cache[guild_id]
            if time.time() < cache['expires']:
                return cache['data']

        # B. Cek Database (Disk)
        config = await self.fetch_one("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
        
        # C. Lazy Insert (Anti-Crash / Race Condition Fix)
        if not config:
            await self.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
            config = await self.fetch_one("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))

        # D. Simpan ke Cache (Agar request berikutnya tidak akses DB lagi)
        if config:
            self._config_cache[guild_id] = {
                'data': config,
                'expires': time.time() + self.TTL
            }
            
        return config

    async def update_config(self, guild_id, announce_id, voice_xp, chat_xp):
        if voice_xp < 0 or chat_xp < 0:
            raise ValueError("XP rates must be nonnegative")
        await self.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
        await self.execute(
            """UPDATE guild_config SET announce_channel_id = ?, voice_xp_val = ?, chat_xp_val = ? 
               WHERE guild_id = ?""",
            (announce_id, voice_xp, chat_xp, guild_id)
        )
        self._invalidate_config_cache(guild_id)

    async def update_guild_xp_config(self, guild_id, announce_id, voice_xp, chat_xp, announcement_mode, min_members_voice):
        """Atomically save every XP setting owned by the setup wizard."""
        if voice_xp < 0 or chat_xp < 0:
            raise ValueError("XP rates must be nonnegative")
        if announcement_mode not in {"quiet", "balanced", "loud"}:
            raise ValueError("announcement_mode is invalid")
        if not isinstance(min_members_voice, int) or min_members_voice < 1:
            raise ValueError("min_members_voice must be a positive integer")
        if not self._conn:
            await self.connect()
        async with self._write_lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._conn.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
                await self._conn.execute(
                    """UPDATE guild_config
                       SET announce_channel_id = ?, voice_xp_val = ?, chat_xp_val = ?,
                           announcement_mode = ?, min_members_voice = ?
                       WHERE guild_id = ?""",
                    (announce_id, voice_xp, chat_xp, announcement_mode, min_members_voice, guild_id),
                )
                await self._conn.commit()
            except Exception as exc:
                await self._conn.rollback()
                self._log_db_failure("ERROR", "DB_WRITE_FAIL", "update_guild_xp_config transaction", exc)
                raise
        self._invalidate_config_cache(guild_id)

    async def is_channel_allowed(self, guild_id, channel_id):
        """Cek apakah channel spesifik diperbolehkan (untuk Voice Engine)."""
        filters = await self.get_filters(guild_id)
        channel_whitelist = [f['target_id'] for f in filters if f['type'] == 'channel' and f['category'] == 'allow']
        channel_blacklist = [f['target_id'] for f in filters if f['type'] == 'channel' and f['category'] == 'exclude']

        if channel_id in channel_blacklist: 
            return False
        if channel_whitelist and channel_id not in channel_whitelist: 
            return False
        return True

    async def add_filter(self, guild_id, target_id, f_type, category):
        await self.execute(
            "INSERT OR REPLACE INTO filters (guild_id, target_id, type, category) VALUES (?, ?, ?, ?)",
            (guild_id, target_id, f_type, category)
        )
        
        self._invalidate_filter_cache(guild_id)
        
    async def remove_filter(self, guild_id, target_id):
        """
        Menghapus filter berdasarkan ID target (Role/Channel).
        Ini akan menghapus target tersebut dari whitelist MAUPUN blacklist sekaligus.
        """
        # Kita tidak pakai f_type/category di WHERE agar pembersihan tuntas
        await self.execute(
            "DELETE FROM filters WHERE guild_id = ? AND target_id = ?",
            (guild_id, target_id)
        )
        
        # Invalidate Cache (Wajib)
        self._invalidate_filter_cache(guild_id)
        
    async def reset_guild_filters(self, guild_id):
        """Menghapus SEMUA filter di server tertentu (Reset)."""
        # 1. Hapus semua row milik guild ini di tabel filters
        await self.execute("DELETE FROM filters WHERE guild_id = ?", (guild_id,))
        
        # 2. [WAJIB] Buang cache lama
        self._invalidate_filter_cache(guild_id)

    async def get_filters(self, guild_id):
        # A. Cek Cache
        if guild_id in self._filter_cache:
            cache = self._filter_cache[guild_id]
            if time.time() < cache['expires']:
                return cache['data']

        # B. Ambil dari DB
        rows = await self.fetch_all("SELECT target_id, type, category FROM filters WHERE guild_id = ?", (guild_id,))

        # C. Simpan ke Cache
        self._filter_cache[guild_id] = {
            'data': rows,
            'expires': time.time() + self.TTL
        }
        return rows

    async def add_reward(self, guild_id, level, role_id):
        await self.execute(
            "INSERT OR REPLACE INTO rewards (guild_id, level_required, role_id) VALUES (?, ?, ?)",
            (guild_id, level, role_id)
        )
        
    async def update_announcement_mode(self, guild_id, mode):
        """Memperbarui mode notifikasi: quiet, balanced, atau loud."""
        await self.execute(
            "UPDATE guild_config SET announcement_mode = ? WHERE guild_id = ?",
            (mode, guild_id)
        )
        
        self._invalidate_config_cache(guild_id)
    
    # --- SOCIAL SAFETY LOGIC ---

    async def is_eligible(self, member, channel):
        """Pengecekan akhir apakah user layak dapat XP."""
        guild_id = member.guild.id
        filters = await self.get_filters(guild_id)
        
        if not await self.is_channel_allowed(guild_id, channel.id): 
            return False

        role_blacklist = [f['target_id'] for f in filters if f['type'] == 'role' and f['category'] == 'exclude']
        role_whitelist = [f['target_id'] for f in filters if f['type'] == 'role' and f['category'] == 'allow']

        member_role_ids = [role.id for role in member.roles]
        if any(r_id in role_blacklist for r_id in member_role_ids): 
            return False
        if role_whitelist and not any(r_id in role_whitelist for r_id in member_role_ids): 
            return False
        
        return True
    
    # --- EVENT SYSTEM LOGIC ---
    async def get_event_config(self, guild_id, event_type):
        """Mengambil konfigurasi event spesifik."""
        return await self.fetch_one(
            "SELECT * FROM event_configs WHERE guild_id = ? AND event_type = ?",
            (guild_id, event_type)
        )

    async def set_event_config(self, guild_id, event_type, col_name, value):
        """Update one setting through the atomic event configuration writer."""
        await self.update_event_config(guild_id, event_type, {col_name: value})

    async def update_event_config(self, guild_id, event_type, values):
        """Atomically create or update one event configuration."""
        allowed_columns = {
            "channel_id", "is_enabled", "message_text", "use_embed",
            "embed_title", "embed_description", "embed_color", "image_url",
        }
        if not values:
            return
        if set(values) - allowed_columns:
            raise ValueError("Invalid event configuration column")
        if not self._conn:
            await self.connect()

        assignments = ", ".join(f"{column} = ?" for column in values)
        parameters = (*values.values(), guild_id, event_type)
        async with self._write_lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._conn.execute(
                    "INSERT OR IGNORE INTO event_configs (guild_id, event_type) VALUES (?, ?)",
                    (guild_id, event_type),
                )
                await self._conn.execute(
                    f"UPDATE event_configs SET {assignments} WHERE guild_id = ? AND event_type = ?",
                    parameters,
                )
                await self._conn.commit()
            except Exception as exc:
                await self._conn.rollback()
                self._log_db_failure("ERROR", "DB_WRITE_FAIL", "update_event_config transaction", exc)
                raise

    async def clear_event_config(self, guild_id, event_type):
        """Remove one complete event configuration after caller confirmation."""
        await self.execute(
            "DELETE FROM event_configs WHERE guild_id = ? AND event_type = ?",
            (guild_id, event_type),
        )

    # --- RESET XP LOGIC ---
    async def reset_guild_xp(self, guild_id):
        """Mereset XP & Level semua member di guild tertentu. Mengembalikan jumlah user yang terdampak."""
        if not self._conn: 
            await self.connect()
        async with self._write_lock:
            cursor = await self._conn.execute(
                "UPDATE users SET xp = 0, level = 0 WHERE guild_id = ?", 
                (guild_id,)
            )
            affected_rows = cursor.rowcount
            await self._conn.commit()
            return affected_rows
    
    async def reset_user_xp(self, guild_id, user_id):
        """Mereset XP satu member spesifik. Return 1 jika berhasil, 0 jika data tidak ditemukan."""
        if not self._conn: 
            await self.connect()
        async with self._write_lock:
            cursor = await self._conn.execute(
                "UPDATE users SET xp = 0, level = 0 WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            affected = cursor.rowcount
            await self._conn.commit()
            return affected
        
    # --- BOT GLOBAL SETTINGS ---
    async def set_bot_setting(self, key, value):
        await self.execute(
            "INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )

    async def get_bot_setting(self, key):
        row = await self.fetch_one("SELECT value FROM bot_settings WHERE key = ?", (key,))
        return row['value'] if row else None
    
    async def get_total_users(self):
        """Menghitung total user yang tercatat di database."""
        row = await self.fetch_one("SELECT COUNT(*) as count FROM users")
        return row['count'] if row else 0

    async def update_user_xp_direct(self, user_id, guild_id, xp_value, mode="add"):
        """
        Mengubah XP user secara langsung.
        param xp_value: Nilai XP yang akan ditambahkan (mode='add') atau nilai akhir (mode='set').
        Return: old_xp, old_level, new_level, new_xp dari transaksi yang sama.
        """
        if mode not in ("add", "set"):
            raise ValueError("mode must be 'add' or 'set'")
        async with self._write_lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._ensure_user_tx(user_id, guild_id)
                cursor = await self._conn.execute("SELECT xp, level FROM users WHERE user_id=? AND guild_id=?", (user_id, guild_id))
                user = await cursor.fetchone()
                old_xp = user["xp"]
                old_level = user["level"]
                new_xp = max(0, old_xp + xp_value if mode == "add" else xp_value)
                from utils.math_utils import calculate_level
                new_level = calculate_level(new_xp)
                await self._conn.execute("UPDATE users SET xp=?, level=? WHERE user_id=? AND guild_id=?", (new_xp,new_level,user_id,guild_id))
                await self._conn.commit()
                return old_xp, old_level, new_level, new_xp
            except Exception as e:
                await self._conn.rollback()
                self._log_db_failure("ERROR", "DB_WRITE_FAIL", "update_user_xp_direct transaction", e)
                raise
    
    async def update_min_members_voice(self, guild_id, value):
        """Update jumlah minimal member untuk validasi Voice XP."""
        if not isinstance(value, int) or value < 1:
            raise ValueError("min_members_voice must be a positive integer")
        await self.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
        await self.execute(
            "UPDATE guild_config SET min_members_voice = ? WHERE guild_id = ?",
            (value, guild_id)
        )
        self._invalidate_config_cache(guild_id)
        
    async def update_weekly_stats(self, guild_id, user_id, xp_add=0, voice_mins_add=0, chat_xp_add=0):
        async with self._write_lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._upsert_weekly_stats_tx(guild_id, user_id, xp_add, voice_mins_add, chat_xp_add)
                await self._conn.commit()
            except Exception as e:
                await self._conn.rollback()
                self._log_db_failure("ERROR", "DB_WRITE_FAIL", "update_weekly_stats transaction", e)
                raise
        
    async def get_weekly_leaderboard(self, guild_id, metric="weekly_voice_mins", limit=10):
        week_key = self.get_current_week_key()
        # Validasi metric agar tidak SQL Injection
        valid_metrics = ["weekly_voice_mins", "weekly_xp"]
        if metric not in valid_metrics: 
            metric = "weekly_voice_mins"
        
        return await self.fetch_all(f"""
            SELECT user_id, weekly_xp, weekly_voice_mins 
            FROM weekly_stats 
            WHERE guild_id = ? AND week_key = ? 
            ORDER BY {metric} DESC 
            LIMIT ?
        """, (guild_id, week_key, limit))
    
    async def get_level_rewards(self, guild_id):
        """Mengambil daftar reward role untuk guild tertentu."""
        # Kita urutkan dari level terkecil ke terbesar
        return await self.fetch_all(
            "SELECT level_required, role_id FROM rewards WHERE guild_id = ? ORDER BY level_required ASC",
            (guild_id,)
        )
    
    # --- HELPER INVALIDATION (PEMBERSIH CACHE) ---
    def _invalidate_config_cache(self, guild_id):
        """Membuang cache config lama agar bot mengambil data baru."""
        self._config_cache.pop(guild_id, None) 

    def _invalidate_filter_cache(self, guild_id):
        """Membuang cache filter lama."""
        if guild_id in self._filter_cache:
            self._filter_cache.pop(guild_id, None)
            
    # --- WEEK KEY HELPER ---
    def get_week_key_for_date(self, dt: datetime) -> str:
        """Helper stabil untuk ubah tanggal apapun jadi 'YYYY-Wxx'."""
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    def get_current_week_key(self):
        """Mengambil key minggu SAAT INI (UTC)."""
        return self.get_week_key_for_date(datetime.now(timezone.utc))
    
    # --- WEEKLY CONFIG METHODS ---
    async def get_weekly_config(self, guild_id):
        """Mengambil konfigurasi weekly recap untuk guild tertentu."""
        return await self.fetch_one(
            "SELECT * FROM weekly_config WHERE guild_id = ?",
            (guild_id,)
        )
    
    async def set_weekly_config(self, guild_id, recap_channel_id=None, is_enabled=None, last_posted_week_key=None):
        """Mengupdate atau membuat konfigurasi weekly recap."""
        # Cek apakah sudah ada konfigurasi
        existing = await self.get_weekly_config(guild_id)
        
        if existing:
            # Update existing
            updates = []
            params = []
            
            if recap_channel_id is not None:
                updates.append("recap_channel_id = ?")
                params.append(recap_channel_id)
            if is_enabled is not None:
                updates.append("is_enabled = ?")
                params.append(is_enabled)
            if last_posted_week_key is not None:
                updates.append("last_posted_week_key = ?")
                params.append(last_posted_week_key)
            
            if updates:
                params.append(guild_id)
                query = f"UPDATE weekly_config SET {', '.join(updates)} WHERE guild_id = ?"
                await self.execute(query, tuple(params))
        else:
            # Insert new
            await self.execute(
                "INSERT INTO weekly_config (guild_id, recap_channel_id, is_enabled, last_posted_week_key) VALUES (?, ?, ?, ?)",
                (guild_id, recap_channel_id or 0, is_enabled or 0, last_posted_week_key or "")
            )
    
    # --- LEFT MEMBERS METHODS ---
    async def save_left_member(self, user_id, guild_id, xp, level, total_voice_mins):
        """Menyimpan data member yang keluar dari server."""
        await self.execute(
            "INSERT OR REPLACE INTO left_members (user_id, guild_id, xp, level, total_voice_mins) VALUES (?, ?, ?, ?, ?)",
            (user_id, guild_id, xp, level, total_voice_mins)
        )
    
    async def get_left_member(self, user_id, guild_id):
        """Mengambil data member yang pernah keluar dari server."""
        return await self.fetch_one(
            "SELECT * FROM left_members WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
    
    # --- GAMIFICATION LOGIC (ACHIEVEMENT, BADGE, TITLE) ---

    async def update_voice_streak(self, user_id, guild_id):
        """
        Update streak harian user.
        Return: Streak terbaru (int).
        """
        # 1. Ambil data terakhir
        user = await self.fetch_one(
            "SELECT voice_streak, last_voice_date FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
        if not user: return 0

        current_streak = user['voice_streak'] or 0
        last_date_str = user['last_voice_date']
        
        # Format tanggal YYYY-MM-DD
        today_date = datetime.now().strftime("%Y-%m-%d")

        new_streak = current_streak

        # 2. Logika Hitung Streak
        if last_date_str == today_date:
            # Sudah login hari ini, streak tidak berubah
            return current_streak
        
        if last_date_str:
            # Cek apakah last_date adalah "kemarin"
            last_dt = datetime.strptime(last_date_str, "%Y-%m-%d")
            today_dt = datetime.strptime(today_date, "%Y-%m-%d")
            delta = (today_dt - last_dt).days

            if delta == 1:
                # Login berturut-turut
                new_streak += 1
            else:
                # Terputus (bolong lebih dari 1 hari)
                new_streak = 1
        else:
            # Baru pertama kali voice
            new_streak = 1

        # 3. Simpan ke DB
        await self.execute(
            "UPDATE users SET voice_streak = ?, last_voice_date = ? WHERE user_id = ? AND guild_id = ?",
            (new_streak, today_date, user_id, guild_id)
        )
        return new_streak

    async def unlock_badge(self, user_id, guild_id, badge_id):
        """
        Memberikan badge ke user.
        Return: True jika baru dapat, False jika sudah punya.
        """

        async with self._write_lock:
            cursor = await self._conn.execute(
                "INSERT OR IGNORE INTO user_badges (user_id, guild_id, badge_id) VALUES (?, ?, ?)",
                (user_id, guild_id, badge_id)
            )
            await self._conn.commit()
            
            return cursor.rowcount > 0

    async def unlock_title(self, user_id, guild_id, title_id):
        """
        Memberikan title (julukan) ke user.
        Return: True jika baru dapat.
        """
        
        async with self._write_lock:
            cursor = await self._conn.execute(
                "INSERT OR IGNORE INTO user_titles (user_id, guild_id, title_id) VALUES (?, ?, ?)",
                (user_id, guild_id, title_id)
            )
            await self._conn.commit()
            return cursor.rowcount > 0

    async def get_user_gamification_profile(self, user_id, guild_id):
        """
        Mengambil data lengkap untuk command /profile dan /rank.
        Mengembalikan: (active_title, list_badges, list_titles)
        """
        # A. Ambil Active Title dari tabel users
        user_row = await self.fetch_one(
            "SELECT active_title FROM users WHERE user_id = ? AND guild_id = ?", 
            (user_id, guild_id)
        )
        active_title = user_row['active_title'] if user_row else None

        # B. Ambil List Badges
        badge_rows = await self.fetch_all(
            "SELECT badge_id FROM user_badges WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
        badges = [r['badge_id'] for r in badge_rows]

        # C. Ambil List Titles
        title_rows = await self.fetch_all(
            "SELECT title_id FROM user_titles WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
        titles = [r['title_id'] for r in title_rows]

        return active_title, badges, titles

    async def set_active_title(self, user_id, guild_id, title_id):
        """Mengganti title yang sedang dipakai."""
        # Validasi: Pastikan user punya title tersebut
        has_title = await self.fetch_one(
            "SELECT 1 FROM user_titles WHERE user_id = ? AND guild_id = ? AND title_id = ?",
            (user_id, guild_id, title_id)
        )
        
        if not has_title and title_id is not None:
            return False # Gagal, user gak punya title ini
            
        await self.execute(
            "UPDATE users SET active_title = ? WHERE user_id = ? AND guild_id = ?",
            (title_id, user_id, guild_id)
        )
        return True
    
    async def delete_left_member(self, user_id, guild_id):
        """Menghapus data member yang sudah kembali ke server."""
        await self.execute(
            "DELETE FROM left_members WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )

    async def claim_weekly_recap(self, guild_id, current_week, now_ts=None, lease_seconds=3600):
        """
        Mencoba 'mengklaim' jatah posting minggu ini secara atomik.
        Return: True jika berhasil klaim (belum diposting), False jika sudah.
        """
        now_ts = now_ts or time.time()
        async with self._write_lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = await self._conn.execute("""INSERT INTO weekly_recap_deliveries
                    (guild_id,week_key,status,claimed_at,attempts) VALUES (?,?,'pending',?,1)
                    ON CONFLICT(guild_id,week_key) DO UPDATE SET status='pending', claimed_at=excluded.claimed_at,
                    attempts=weekly_recap_deliveries.attempts+1,last_error=NULL
                    WHERE weekly_recap_deliveries.status IN ('failed','pending')
                    AND (weekly_recap_deliveries.status='failed' OR weekly_recap_deliveries.claimed_at <= ?)""",
                    (guild_id,current_week,now_ts,now_ts-lease_seconds))
                await self._conn.commit()
                return cursor.rowcount == 1
            except Exception as e:
                await self._conn.rollback()
                self._log_db_failure("ERROR", "DB_WRITE_FAIL", "claim_weekly_recap transaction", e)
                raise

    async def finish_weekly_recap(self, guild_id, week_key, status, error=None):
        if status not in ("posted", "empty", "failed"):
            raise ValueError("invalid weekly recap status")
        now = time.time()
        async with self._write_lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._conn.execute("UPDATE weekly_recap_deliveries SET status=?, posted_at=?, last_error=? WHERE guild_id=? AND week_key=?", (status, now if status == "posted" else None, str(error)[:500] if error else None, guild_id, week_key))
                if status == "posted":
                    await self._conn.execute("UPDATE weekly_config SET last_posted_week_key=? WHERE guild_id=?", (week_key,guild_id))
                await self._conn.commit()
            except Exception as e:
                await self._conn.rollback()
                self._log_db_failure("ERROR", "DB_WRITE_FAIL", "finish_weekly_recap transaction", e)
                raise
        
    async def _run_migrations(self):
        """Menjalankan migrasi database secara aman & atomic."""
        async with self._write_lock:
            # Mulai Transaksi Eksklusif (Kunci DB total)
            await self._conn.execute("BEGIN IMMEDIATE")
            
            try:
                # Cek versi saat ini
                cursor = await self._conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'")
                row = await cursor.fetchone()
                current_version = row[0] if row else 0
                
                # Cek apakah ada versi baru yang perlu diapply
                # MIGRATIONS adalah dictionary yang kita buat di Langkah 1
                for version in sorted(MIGRATIONS):
                    if version > current_version:
                        # Jalankan fungsi migrasi
                        await MIGRATIONS[version](self._conn)
                        
                        # Update versi di DB
                        await self._conn.execute("UPDATE schema_meta SET value=? WHERE key='schema_version'", (version,))
                        print(f"✅ Database upgraded to v{version}")
                
                # Commit semua perubahan JIKA DAN HANYA JIKA semua sukses
                await self._conn.commit()
                
            except Exception as e:
                print(f"❌ MIGRATION FAILED: {e}")
                # Rollback jika ada error (DB kembali ke keadaan semula sebelum migrasi)
                await self._conn.rollback()
                # Raise error biar bot STOP dan admin sadar ada masalah
                raise RuntimeError("Database migration failed. Bot shutdown for safety.")
            

    # --- GLOBAL USER STATE (JIROMI INTRO) ---

    async def should_send_global_intro(self, user_id):
        """
        Cek apakah user sudah pernah menerima intro Jiromi (Global Check).
        Return: True jika BELUM pernah (boleh kirim), False jika SUDAH.
        """
        row = await self.fetch_one(
            "SELECT has_seen_jiromi_intro FROM user_globals WHERE user_id = ?", 
            (user_id,)
        )
        if not row:
            return True # User belum ada di tabel global -> Kirim Intro
        
        return row['has_seen_jiromi_intro'] == 0

    async def mark_global_intro_seen(self, user_id):
        """Tandai user sudah menerima intro (Atomic Insert/Update)."""
        now = datetime.now().isoformat()
        async with self._write_lock:
            await self._conn.execute("""
                INSERT INTO user_globals (user_id, has_seen_jiromi_intro, first_intro_at)
                VALUES (?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET 
                    has_seen_jiromi_intro = 1,
                    first_intro_at = excluded.first_intro_at
            """, (user_id, now))
            await self._conn.commit()
