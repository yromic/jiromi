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

# Update Dictionary MIGRATIONS
MIGRATIONS = {
    2: migrate_v2_weekly_chat_xp,
    3: migrate_v3_gamification,
    4: migrate_v4_global_users # <--- Tambahkan ini
}

async def init_db():
    """Wrapper untuk inisialisasi database global (Thread-safe)."""
    global _db_instance
    # Pastikan hanya 1 proses yang bisa init dalam satu waktu
    async with _db_init_lock:
        if _db_instance is None:
            _db_instance = DatabaseHandler()
            await _db_instance.connect()
    return _db_instance

async def close_db():
    """Wrapper untuk menutup database global."""
    global _db_instance
    if _db_instance:
        await _db_instance.close()
        _db_instance = None

class DatabaseHandler:
    def __init__(self, db_path="database/schema.db"):
        self.db_path = db_path
        self._conn = None  # Single Connection
        self._write_lock = asyncio.Lock()  # Serialize Writes
        self._config_cache = {} 
        self._filter_cache = {}
        self.TTL = 60

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
            async with self._write_lock:
                await self._conn.execute(query, vars)
                await self._conn.commit()
        except Exception as e:
            print(f"❌ DB WRITE ERROR: {e} | Query: {query}")
            raise e # Re-raise agar caller tau errornya

    async def fetch_one(self, query, vars=()):
        """Execute READ query (DENGAN Lock Write sesuai saran Senior)."""
        if not self._conn: 
            await self.connect()

        try:
            # [FIX SENIOR 4] Kembalikan Lock agar thread-safe total
            async with self._write_lock:
                async with self._conn.execute(query, vars) as cursor:
                    return await cursor.fetchone()
        except Exception as e:
            print(f"❌ DB READ ERROR: {e}")
            return None

    async def fetch_all(self, query, vars=()):
        """Execute READ ALL query (DENGAN Lock Write sesuai saran Senior)."""
        if not self._conn: 
            await self.connect()

        try:
            # [FIX SENIOR 4] Kembalikan Lock agar thread-safe total
            async with self._write_lock:
                async with self._conn.execute(query, vars) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            print(f"❌ DB READ ALL ERROR: {e}")
            return []
    # --- USER DATA & XP LOGIC ---

    async def get_user_data(self, user_id, guild_id):
        user = await self.fetch_one(
            "SELECT xp, level, total_voice_mins, last_chat_ts FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
        if not user:
            # Jika user baru, buat row baru
            await self.execute("INSERT INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
            # Return dict default
            return {"xp": 0, "level": 0, "total_voice_mins": 0, "last_chat_ts": 0}
        
        # [FIX 3] Konversi aiosqlite.Row menjadi standard Dict agar konsisten
        return dict(user)

    async def add_voice_time(self, user_id, guild_id, minutes, xp_per_min):
        total_xp_gain = minutes * xp_per_min
        
        async with self._write_lock:
            # 1. Atomic Update XP & Voice Mins
            await self._conn.execute(
                """
                UPDATE users 
                SET xp = xp + ?, total_voice_mins = total_voice_mins + ? 
                WHERE user_id = ? AND guild_id = ?
                """,
                (total_xp_gain, minutes, user_id, guild_id)
            )
            await self._conn.commit()

            # 2. Ambil data terbaru
            cursor = await self._conn.execute(
                "SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = await cursor.fetchone()
            
            # Handle user baru jika belum ada record
            if not row:
                 # Logic insert user baru bisa ditaruh di sini atau di event listener
                 return {"old_level": 0, "new_level": 0}

            current_xp = row['xp']
            old_level = row['level']

            from utils.math_utils import calculate_level
            new_level = calculate_level(current_xp)

            if new_level > old_level:
                await self._conn.execute(
                    "UPDATE users SET level = ? WHERE user_id = ? AND guild_id = ?",
                    (new_level, user_id, guild_id)
                )
                await self._conn.commit()

            return {"old_level": old_level, "new_level": new_level}

    async def add_chat_xp(self, user_id, guild_id, xp_amount):
        # Gunakan Lock Write karena kita melakukan transaksi (Read+Write sekaligus)
        async with self._write_lock:
            # 1. Atomic Update: Biarkan SQL yang nambah, jangan Python
            # Kita update XP dan timestamp sekaligus
            await self._conn.execute(
                """
                UPDATE users 
                SET xp = xp + ?, last_chat_ts = ? 
                WHERE user_id = ? AND guild_id = ?
                """,
                (xp_amount, time.time(), user_id, guild_id)
            )
            await self._conn.commit()

            # 2. Ambil data terbaru setelah update untuk cek level up
            cursor = await self._conn.execute(
                "SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = await cursor.fetchone()
            
            if not row:
                # Edge case: User belum ada di DB (jarang terjadi karena ada check eligible)
                # Insert manual jika perlu, atau return
                return {"old_level": 0, "new_level": 0}

            current_xp = row['xp']
            old_level = row['level']

            # 3. Hitung Level Baru
            from utils.math_utils import calculate_level
            new_level = calculate_level(current_xp)

            # 4. Jika Level Naik, Update Level
            if new_level > old_level:
                await self._conn.execute(
                    "UPDATE users SET level = ? WHERE user_id = ? AND guild_id = ?",
                    (new_level, user_id, guild_id)
                )
                await self._conn.commit()
            
            return {"old_level": old_level, "new_level": new_level}

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
        await self.execute(
            """UPDATE guild_config SET announce_channel_id = ?, voice_xp_val = ?, chat_xp_val = ? 
               WHERE guild_id = ?""",
            (announce_id, voice_xp, chat_xp, guild_id)
        )
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
        """Update satu kolom konfigurasi event."""
        
        # [FIX 2] Security Whitelist: Cegah SQL Injection
        ALLOWED_COLS = {
            "channel_id", "is_enabled", "message_text", "use_embed",
            "embed_title", "embed_description", "embed_color", "image_url"
        }
        if col_name not in ALLOWED_COLS:
            raise ValueError(f"❌ Security Alert: Kolom '{col_name}' tidak valid/diizinkan.")

        # 1. Pastikan row ada
        exists = await self.fetch_one(
            "SELECT 1 FROM event_configs WHERE guild_id = ? AND event_type = ?",
            (guild_id, event_type)
        )
        if not exists:
            await self.execute(
                "INSERT INTO event_configs (guild_id, event_type) VALUES (?, ?)",
                (guild_id, event_type)
            )
        
        # 2. Update kolom target (Aman karena col_name sudah divalidasi)
        query = f"UPDATE event_configs SET {col_name} = ? WHERE guild_id = ? AND event_type = ?"
        await self.execute(query, (value, guild_id, event_type))
    
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
        """
        user = await self.get_user_data(user_id, guild_id)
        current_xp = user['xp']
        
        if mode == "add":
            new_xp = current_xp + xp_value
        else: # mode "set"
            new_xp = xp_value
        
        if new_xp < 0: 
            new_xp = 0

        from utils.math_utils import calculate_level
        new_level = calculate_level(new_xp)

        await self.execute(
            "UPDATE users SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?",
            (new_xp, new_level, user_id, guild_id)
        )
        
        return user['level'], new_level, new_xp
    
    async def update_min_members_voice(self, guild_id, value):
        """Update jumlah minimal member untuk validasi Voice XP."""
        await self.execute(
            "UPDATE guild_config SET min_members_voice = ? WHERE guild_id = ?",
            (value, guild_id)
        )
        self._invalidate_config_cache(guild_id)
        
    async def update_weekly_stats(self, guild_id, user_id, xp_add=0, voice_mins_add=0, chat_xp_add=0):
        week_key = self.get_current_week_key()
        now_ts = time.time()
        
        # SQL Upsert dengan kolom weekly_chat_xp
        await self.execute("""
            INSERT INTO weekly_stats (guild_id, user_id, week_key, weekly_xp, weekly_voice_mins, weekly_chat_xp, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, week_key) 
            DO UPDATE SET 
                weekly_xp = weekly_xp + excluded.weekly_xp,
                weekly_voice_mins = weekly_voice_mins + excluded.weekly_voice_mins,
                weekly_chat_xp = weekly_chat_xp + excluded.weekly_chat_xp,
                updated_at = excluded.updated_at
        """, (guild_id, user_id, week_key, xp_add, voice_mins_add, chat_xp_add, now_ts))
        
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
        # Gunakan INSERT OR IGNORE agar tidak error jika duplikat
        cursor = await self._conn.execute(
            "INSERT OR IGNORE INTO user_badges (user_id, guild_id, badge_id) VALUES (?, ?, ?)",
            (user_id, guild_id, badge_id)
        )
        await self._conn.commit()
        
        # Jika rowcount > 0 artinya ada data baru masuk (baru unlock)
        return cursor.rowcount > 0

    async def unlock_title(self, user_id, guild_id, title_id):
        """
        Memberikan title (julukan) ke user.
        Return: True jika baru dapat.
        """
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

    async def claim_weekly_recap(self, guild_id, current_week):
        """
        Mencoba 'mengklaim' jatah posting minggu ini secara atomik.
        Return: True jika berhasil klaim (belum diposting), False jika sudah.
        """
        # Gunakan lock write karena ini operasi UPDATE
        async with self._write_lock:
            # Logic SQL: Update HANYA JIKA minggu di DB beda dengan minggu sekarang
            query = """
                UPDATE weekly_config
                SET last_posted_week_key = ?
                WHERE guild_id = ? 
                AND (last_posted_week_key IS NULL OR last_posted_week_key != ?)
            """
            cursor = await self._conn.execute(query, (current_week, guild_id, current_week))
            await self._conn.commit()
            
            # Jika rowcount = 1, artinya update berhasil (kita yang menang)
            # Jika rowcount = 0, artinya kondisi WHERE tidak terpenuhi (sudah diposting orang lain/loop sebelumnya)
            return cursor.rowcount == 1
        
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