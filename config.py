import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("SSB_CONFIG", os.path.join(BASE, "config.json"))

DEFAULTS = {
    "wecom_webhook": "",
    "serverchan_key": "",
    "keywords": ["森兰", "中铁", "桂竹", "海上", "西派", "海华智", "万安里"],
    "ignore": {"4594": "森兰星遇公寓(新展城店)", "3025": "城家高级公寓（森兰洲海路地铁站店）"},
    "district_id": "",
    "district_name": "全市",
    "heartbeat_hours": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22],
    "quiet_start": 0,
    "quiet_end": 8,
    "default_base_days": 1,
    "sched_start": 8,
    "sched_end": 19,
    "sched_step": 20,
    "sched_extra_hours": [20, 21, 22, 0],
    "push": {
        "total_change": True,
        "district_change": False,
        "districts": [],
        "notice": True,
        "keywords": [],
        "pd_updown": False,
        "pd_keywords": [],
    },
}


def load():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
