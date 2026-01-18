# utils/math_utils.py
import math

def calculate_level(xp):
    """
    Rumus: Level = log(XP) / log(multiplier)
    Menggunakan multiplier 3 sesuai permintaan untuk kurva yang melambat di akhir.
    """
    if xp < 10: return 0
    level = math.log(xp) / math.log(3)
    return int(level)

def xp_for_next_level(level):
    """Menghitung butuh berapa total XP untuk mencapai level berikutnya"""
    return int(3 ** (level + 1))
