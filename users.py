import os
import json
import hmac
import hashlib
import re
import subprocess
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
USERS_FILE = os.path.join(DATA, "users.json")
REG_FILE = os.path.join(DATA, "reg_ip.json")
QUOTA_FILE = os.path.join(DATA, "geo_quota.json")
BJ = timezone(timedelta(hours=8))


def now_bj():
    return datetime.now(BJ)


def today():
    return now_bj().strftime("%Y-%m-%d")


def _load(path, default):
    try:
        if os.path.exists(path):
            return json.load(open(path))
    except Exception:
        pass
    return default


def _save(path, d):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(d, open(path, "w"), ensure_ascii=False, indent=1)


def valid_email(e):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", (e or "").strip()))


_MX_CACHE = {}


def email_domain_ok(email):
    """尽力校验邮箱域名能收信（MX 或 A 记录）。工具不可用则放行。"""
    try:
        domain = (email or "").split("@")[-1].strip().lower()
    except Exception:
        return False
    if not domain or "." not in domain:
        return False
    if domain in _MX_CACHE:
        return _MX_CACHE[domain]
    ok = True
    try:
        mx = subprocess.run(["dig", "+short", "MX", domain], capture_output=True, text=True, timeout=6).stdout.strip()
        if mx:
            ok = True
        else:
            a = subprocess.run(["dig", "+short", "A", domain], capture_output=True, text=True, timeout=6).stdout.strip()
            ok = bool(a)
    except Exception:
        ok = True
    _MX_CACHE[domain] = ok
    return ok


def hash_pw(pw, salt=None):
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), 150000).hex()
    return salt, h


def verify_pw(pw, salt, h):
    try:
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), 150000).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def load_users():
    return _load(USERS_FILE, {})


def save_users(d):
    _save(USERS_FILE, d)


def get_user(email):
    return load_users().get((email or "").strip().lower())


def create_user(email, pw, name):
    email = email.strip().lower()
    d = load_users()
    salt, h = hash_pw(pw)
    u = {
        "email": email,
        "name": (name or "").strip() or email.split("@")[0],
        "salt": salt,
        "pw": h,
        "created_at": now_bj().isoformat(timespec="seconds"),
        "role": "user",
        "favorites": [],
        "push": {"serverchan": "", "hours": []},
        "push_day": "",
        "push_count": 0,
    }
    d[email] = u
    save_users(d)
    return u


def update_user(email, **fields):
    d = load_users()
    email = email.strip().lower()
    if email not in d:
        return None
    d[email].update(fields)
    save_users(d)
    return d[email]


def reg_allowed(ip):
    d = _load(REG_FILE, {})
    return today() not in (d.get(ip) or [])


def reg_record(ip):
    d = _load(REG_FILE, {})
    days = [x for x in (d.get(ip) or []) if x >= (now_bj() - timedelta(days=7)).strftime("%Y-%m-%d")]
    if today() not in days:
        days.append(today())
    d[ip] = days
    _save(REG_FILE, d)


def add_favorite(email, key, limit=5):
    d = load_users()
    u = d.get(email)
    if not u:
        return False, "用户不存在"
    favs = u.get("favorites") or []
    if key in favs:
        return True, "已加入对比"
    if len(favs) >= limit:
        return False, f"最多对比 {limit} 个"
    favs.append(key)
    u["favorites"] = favs
    save_users(d)
    return True, "已加入对比"


def remove_favorite(email, key):
    d = load_users()
    u = d.get(email)
    if not u:
        return False
    favs = [x for x in (u.get("favorites") or []) if x != key]
    u["favorites"] = favs
    save_users(d)
    return True


def push_count_today(u):
    if not u:
        return 0
    if u.get("push_day") != today():
        return 0
    return int(u.get("push_count") or 0)


def push_take(email, limit=5):
    d = load_users()
    u = d.get(email)
    if not u:
        return False, 0
    if u.get("push_day") != today():
        u["push_day"] = today()
        u["push_count"] = 0
    n = int(u.get("push_count") or 0)
    if n >= limit:
        save_users(d)
        return False, n
    u["push_count"] = n + 1
    save_users(d)
    return True, n + 1


def quota_take(email, limit=100, global_limit=5000):
    """按用户计数（100/天）+ 全局兜底；返回 (ok, used, reason)"""
    d = _load(QUOTA_FILE, {})
    if d.get("date") != today():
        d = {"date": today(), "users": {}, "global": 0}
    users = d.setdefault("users", {})
    g = int(d.get("global") or 0)
    if g >= global_limit:
        return False, int(users.get(email, 0)), "global"
    n = int(users.get(email, 0))
    if n >= limit:
        return False, n, "user"
    users[email] = n + 1
    d["global"] = g + 1
    _save(QUOTA_FILE, d)
    return True, n + 1, ""
