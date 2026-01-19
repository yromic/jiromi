# utils/db_handler.py
import aiosqlite
import os
import time
import asyncio
from datetime import datetime, timezone, timedelta

# Variabel Global untuk menyimpan instance DB
_db_instance = None
_db_init_lock = asyncio.Lock()

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

        # Connect sekali saja
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row # Agar hasil query bisa diakses via nama kolom

        # PRAGMA Optimization (Saran Senior)
        await self._conn.execute("PRAGMA journal_mode=WAL;") # Concurrency
        await self._conn.execute("PRAGMA busy_timeout=3000;") # Retry tolerance 3s
        await self._conn.execute("PRAGMA synchronous=NORMAL;") # Performance
        await self._conn.commit()

        # Init Schema
        await self._init_tables()
        print("✅ Database Connected (WAL Mode + Shared Connection)")

    async def close(self):
        """Menutup koneksi."""
        if self._conn:
            await self._conn.close()
            print("✅ Database Closed")

    async def _init_tables(self):
        """Membuat tabel & index jika belum ada."""
        # --- TABEL (Schema Lama Tetap Aman) ---
        queries = [
            # Users
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER, guild_id INTEGER, xp INTEGER DEFAULT 0, 
                level INTEGER DEFAULT 0, total_voice_mins INTEGER DEFAULT 0,
                last_chat_ts REAL DEFAULT 0, PRIMARY KEY (user_id, guild_id)
            )""",
            # Config
            """CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY, announce_channel_id INTEGER,
                chat_xp_val INTEGER DEFAULT 5, voice_xp_val INTEGER DEFAULT 10, 
                min_members_voice INTEGER DEFAULT 2, announcement_mode TEXT DEFAULT 'balanced'
            )""",
            # Filters
            """CREATE TABLE IF NOT EXISTS filters (
                guild_id INTEGER, target_id INTEGER, type TEXT, category TEXT,
                PRIMARY KEY (guild_id, target_id, category)
            )""",
            # Rewards
            """CREATE TABLE IF NOT EXISTS rewards (
                guild_id INTEGER, level_required INTEGER, role_id INTEGER,
                PRIMARY KEY (guild_id, level_required)
            )""",
            # Left Members
            """CREATE TABLE IF NOT EXISTS left_members (
                user_id INTEGER, guild_id INTEGER, xp INTEGER, level INTEGER, 
                total_voice_mins INTEGER, left_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            )""",
            # Event Config
            """CREATE TABLE IF NOT EXISTS event_configs (
                guild_id INTEGER, event_type TEXT, channel_id INTEGER,
                is_enabled INTEGER DEFAULT 0, message_text TEXT, use_embed INTEGER DEFAULT 0,
                embed_title TEXT, embed_description TEXT, embed_color INTEGER DEFAULT 0,
                image_url TEXT, PRIMARY KEY (guild_id, event_type)
            )""",
            # Bot Settings
            """CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)""",
            # Weekly Stats
            """CREATE TABLE IF NOT EXISTS weekly_stats (
                guild_id INTEGER, user_id INTEGER, week_key TEXT,                 
                weekly_xp INTEGER DEFAULT 0, weekly_voice_mins INTEGER DEFAULT 0,
                weekly_chat_xp INTEGER DEFAULT 0, updated_at REAL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, week_key)
            )""",
            # Weekly Config
            """CREATE TABLE IF NOT EXISTS weekly_config (
                guild_id INTEGER PRIMARY KEY, recap_channel_id INTEGER,
                is_enabled INTEGER DEFAULT 0, last_posted_week_key TEXT
            )"""
        ]
        
        # --- INDEXING (Saran Senior Step E) ---
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_xp ON users(guild_id, xp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_weekly_stats_rank ON weekly_stats(guild_id, week_key, weekly_voice_mins DESC)",
            "CREATE INDEX IF NOT EXISTS idx_filters_lookup ON filters(guild_id, type)"
        ]

        async with self._write_lock:
            # 1. Buat Tabel
            for q in queries:
                await self._conn.execute(q)
            
            # 2. [FIX 4] Migrasi Cerdas: Cek dulu apakah kolom sudah ada
            # Cek kolom weekly_chat_xp di tabel weekly_stats
            async with self._conn.execute("PRAGMA table_info(weekly_stats)") as cursor:
                columns = await cursor.fetchall()
                # columns[1] biasanya adalah nama kolom
                col_names = [col[1] for col in columns]
                
                if 'weekly_chat_xp' not in col_names:
                    print("⚠️ Migrating DB: Adding weekly_chat_xp column...")
                    await self._conn.execute("ALTER TABLE weekly_stats ADD COLUMN weekly_chat_xp INTEGER DEFAULT 0")

            # 3. Buat Index
            for idx in indexes:
                await self._conn.execute(idx)
            
            await self._conn.commit()

    # --- CORE QUERY METHODS (Revised) ---

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
        """Execute READ query."""
        if not self._conn: 
            await self.connect()

        try:
            # [FIX] Tambahkan Lock di sini agar tidak tabrakan dengan VACUUM
            async with self._write_lock:
                async with self._conn.execute(query, vars) as cursor:
                    return await cursor.fetchone()
        except Exception as e:
            print(f"❌ DB READ ERROR: {e}")
            return None

    async def fetch_all(self, query, vars=()):
        """Execute READ ALL query."""
        if not self._conn: 
            await self.connect()

        try:
            # [FIX] Tambahkan Lock di sini juga
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
        # Transaction implicit via write lock di execute
        user = await self.get_user_data(user_id, guild_id)
        new_xp = user['xp'] + (minutes * xp_per_min)
        new_mins = user['total_voice_mins'] + minutes
        
        from utils.math_utils import calculate_level
        new_level = calculate_level(new_xp)

        await self.execute(
            "UPDATE users SET xp = ?, level = ?, total_voice_mins = ? WHERE user_id = ? AND guild_id = ?",
            (new_xp, new_level, new_mins, user_id, guild_id)
        )
        return {"old_level": user['level'], "new_level": new_level}

    async def add_chat_xp(self, user_id, guild_id, xp_amount):
        user = await self.get_user_data(user_id, guild_id)
        new_xp = user['xp'] + xp_amount
        from utils.math_utils import calculate_level
        new_level = calculate_level(new_xp)
        
        await self.execute(
            "UPDATE users SET xp = ?, level = ?, last_chat_ts = ? WHERE user_id = ? AND guild_id = ?",
            (new_xp, new_level, time.time(), user_id, guild_id)
        )
        return {"old_level": user['level'], "new_level": new_level}

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
    
    async def delete_left_member(self, user_id, guild_id):
        """Menghapus data member yang sudah kembali ke server."""
        await self.execute(
            "DELETE FROM left_members WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )