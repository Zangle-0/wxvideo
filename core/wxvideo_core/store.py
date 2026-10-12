"""本地存储（SQLite）：视频元数据、每次抓取到的 url/decode_key、下载记录、设置、事件。

注意：`decode_key` 与下载地址是**每次抓取才有效**的（同一视频不同次请求会返回新的
url 与 decode_key），所以按 capture 存，下载时用最新一条 capture。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Optional

APP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "wxvideo"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos(
  object_id   TEXT PRIMARY KEY,
  author      TEXT,
  title       TEXT,
  duration_ms INTEGER,
  cover_url   TEXT,
  specs_json  TEXT,
  first_seen  REAL
);
CREATE TABLE IF NOT EXISTS captures(
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  object_id   TEXT,
  url         TEXT,
  url_token   TEXT,
  decode_key  TEXT,
  file_size   INTEGER,
  captured_at REAL
);
CREATE INDEX IF NOT EXISTS idx_captures_obj ON captures(object_id, captured_at DESC);
CREATE TABLE IF NOT EXISTS downloads(
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  object_id   TEXT,
  fmt         TEXT,
  path        TEXT,
  bytes       INTEGER,
  status      TEXT,
  updated_at  REAL
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS events(ts REAL, level TEXT, msg TEXT);
"""


def db_path() -> str:
    return os.path.join(APP_DIR, "wxvideo.db")


class Store:
    def __init__(self, path: Optional[str] = None):
        self.path = path or db_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        # v1: 早期把 video_play_len(秒) 当毫秒存了，这里把明显是秒的值 *1000 修正
        if self.get_setting("mig_duration_v1"):
            return
        self.conn.execute(
            "UPDATE videos SET duration_ms = duration_ms * 1000 "
            "WHERE duration_ms > 0 AND duration_ms < 3600"
        )
        self.conn.commit()
        self.set_setting("mig_duration_v1", True)

    # ---- videos ---- #
    def upsert_video(self, *, object_id: str, author: str, title: str,
                     duration_ms: int = 0, cover_url: str = "",
                     specs: Optional[list] = None) -> None:
        self.conn.execute(
            "INSERT INTO videos(object_id,author,title,duration_ms,cover_url,specs_json,first_seen) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(object_id) DO UPDATE SET "
            "author=excluded.author, title=excluded.title, duration_ms=excluded.duration_ms, "
            "cover_url=excluded.cover_url, specs_json=excluded.specs_json",
            (object_id, author, title, duration_ms, cover_url,
             json.dumps(specs or [], ensure_ascii=False), time.time()),
        )
        self.conn.commit()

    def add_capture(self, *, object_id: str, url: str, url_token: str,
                    decode_key: str, file_size: int) -> None:
        self.conn.execute(
            "INSERT INTO captures(object_id,url,url_token,decode_key,file_size,captured_at) "
            "VALUES(?,?,?,?,?,?)",
            (object_id, url, url_token, str(decode_key), file_size, time.time()),
        )
        self.conn.commit()

    def latest_capture(self, object_id: str) -> Optional[dict]:
        cur = self.conn.execute(
            "SELECT * FROM captures WHERE object_id=? ORDER BY captured_at DESC LIMIT 1",
            (object_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_videos(self, limit: int = 200) -> list[dict]:
        cur = self.conn.execute(
            "SELECT v.*, (SELECT MAX(captured_at) FROM captures c WHERE c.object_id=v.object_id) AS last_capture "
            "FROM videos v ORDER BY last_capture DESC NULLS LAST, first_seen DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_video(self, object_id: str) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM videos WHERE object_id=?", (object_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    # ---- downloads ---- #
    def set_download(self, *, object_id: str, fmt: str, path: str = "",
                     bytes_: int = 0, status: str = "pending") -> int:
        cur = self.conn.execute(
            "INSERT INTO downloads(object_id,fmt,path,bytes,status,updated_at) VALUES(?,?,?,?,?,?)",
            (object_id, fmt, path, bytes_, status, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_download(self, dl_id: int, **kw: Any) -> None:
        if not kw:
            return
        cols = ", ".join(f"{k}=?" for k in kw)
        self.conn.execute(
            f"UPDATE downloads SET {cols}, updated_at=? WHERE id=?",
            (*kw.values(), time.time(), dl_id),
        )
        self.conn.commit()

    # ---- settings / events ---- #
    def set_setting(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        cur = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        r = cur.fetchone()
        return json.loads(r["value"]) if r else default

    def log(self, level: str, msg: str) -> None:
        self.conn.execute("INSERT INTO events(ts,level,msg) VALUES(?,?,?)",
                          (time.time(), level, msg))
        self.conn.commit()
