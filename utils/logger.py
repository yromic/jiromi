import json
import os
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

class JiromiLogger:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        self.jsonl_file = os.path.join(log_dir, "jiromi.jsonl")
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

    def _get_timestamp(self):
        # Format ISO like: 2026-01-18 14:30:05
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write_jsonl(self, level, event_type, data):
        entry = {
            "ts": datetime.now().isoformat(),
            "level": level,
            "type": event_type,
            **data 
        }
        try:
            with open(self.jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"❌ LOG FILE ERROR: {e}")

    # --- TIPE LOGGING (Sekarang pakai Timestamp di Console) ---

    def info(self, event_type, message, **kwargs):
        ts = self._get_timestamp()
        # [FIX 1] Tambah {ts} di depan
        print(f"{Fore.GREEN}{ts} [INFO] [{event_type}]{Style.RESET_ALL} {message}")
        self._write_jsonl("INFO", event_type, {"msg": message, **kwargs})

    def audit(self, event_type, message, **kwargs):
        ts = self._get_timestamp()
        print(f"{Fore.YELLOW}{ts} [AUDIT] [{event_type}]{Style.RESET_ALL} {message}")
        self._write_jsonl("AUDIT", event_type, {"msg": message, **kwargs})

    def error(self, event_type, message, error_obj=None, **kwargs):
        ts = self._get_timestamp()
        err_text = f" | {error_obj}" if error_obj else ""
        print(f"{Fore.RED}{ts} [ERROR] [{event_type}]{Style.RESET_ALL} {message}{err_text}")
        
        err_detail = str(error_obj) if error_obj else None
        self._write_jsonl("ERROR", event_type, {"msg": message, "error": err_detail, **kwargs})

    def stat(self, stats_data):
        ts = self._get_timestamp()
        parts = [f"{k}={v}" for k, v in stats_data.items()]
        line = " ".join(parts)
        # [FIX 1] Tambah {ts}
        print(f"{Fore.CYAN}{ts} [STAT] {line}{Style.RESET_ALL}")
        self._write_jsonl("STAT", "INTERVAL_SUMMARY", stats_data)