"""SQLite database management for AdWhisper."""

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

class Database:
    def __init__(self, db_path: str = "data/scanner.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_schema(self) -> None:
        """Create tables if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT,
                start_date TEXT,
                end_date TEXT,
                is_all_time INTEGER DEFAULT 0,
                min_views INTEGER DEFAULT 2000,
                status TEXT DEFAULT 'pending',
                total_found INTEGER DEFAULT 0,
                filtered_views INTEGER DEFAULT 0,
                filtered_dates INTEGER DEFAULT 0,
                processed INTEGER DEFAULT 0,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                author TEXT,
                title TEXT,
                views INTEGER DEFAULT 0,
                upload_date TEXT,
                upload_timestamp INTEGER,
                duration REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                local_audio_path TEXT,
                scanned_at TEXT,
                error_message TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                audio_type TEXT,
                full_text TEXT,
                segments_json TEXT,
                language TEXT,
                language_probability REAL,
                created_at TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                variant TEXT,
                matched_phrase TEXT,
                start_time REAL,
                end_time REAL,
                timecode_str TEXT,
                confidence REAL,
                method TEXT,
                full_transcription TEXT,
                is_doubtful INTEGER DEFAULT 0,
                reprocessed_with_demucs INTEGER DEFAULT 0,
                verification_notes TEXT,
                created_at TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
            )
            """)

            # Create indices for fast lookup
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_variant ON matches(variant)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_video_id ON matches(video_id)")
            conn.commit()

    # Scan history operations
    def create_scan(self, account: str, start_date: Optional[str], end_date: Optional[str],
                    is_all_time: bool, min_views: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO scans (account, start_date, end_date, is_all_time, min_views, status, started_at)
            VALUES (?, ?, ?, ?, ?, 'running', ?)
            """, (account, start_date, end_date, 1 if is_all_time else 0, min_views, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid

    def update_scan_progress(self, scan_id: int, total_found: int = None,
                             filtered_views: int = None, filtered_dates: int = None,
                             processed: int = None, status: str = None, error_message: str = None) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            if total_found is not None:
                updates.append("total_found = ?")
                params.append(total_found)
            if filtered_views is not None:
                updates.append("filtered_views = ?")
                params.append(filtered_views)
            if filtered_dates is not None:
                updates.append("filtered_dates = ?")
                params.append(filtered_dates)
            if processed is not None:
                updates.append("processed = ?")
                params.append(processed)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
                if status in ("completed", "failed", "interrupted"):
                    updates.append("completed_at = ?")
                    params.append(datetime.now().isoformat())
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            if updates:
                params.append(scan_id)
                cursor.execute(f"UPDATE scans SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()

    def get_latest_scans(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # Video operations
    def save_video(self, video_id: str, url: str, author: str, title: str,
                   views: int, upload_date: str, upload_timestamp: int,
                   status: str = 'pending', error_message: str = None) -> bool:
        """Insert or update video. Returns True if inserted as new, False if already existed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, status FROM videos WHERE id = ?", (video_id,))
            row = cursor.fetchone()
            now = datetime.now().isoformat()
            if row:
                old_status = row["status"]
                # If explicitly marked as filtered (views or date), update status accordingly
                if status in ("filtered_date", "filtered_views"):
                    new_status = status
                elif old_status == "analyzed":
                    new_status = "analyzed"
                else:
                    new_status = status

                cursor.execute("""
                UPDATE videos 
                SET views = ?, upload_date = ?, upload_timestamp = ?, status = ?, scanned_at = ?, error_message = COALESCE(?, error_message)
                WHERE id = ?
                """, (views, upload_date, upload_timestamp, new_status, now, error_message, video_id))
                conn.commit()
                return False
            else:
                cursor.execute("""
                INSERT INTO videos (id, url, author, title, views, upload_date, upload_timestamp, status, scanned_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (video_id, url, author, title, views, upload_date, upload_timestamp, status, now, error_message))
                conn.commit()
                return True

    def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_video_status(self, video_id: str, status: str, duration: float = None,
                            local_audio_path: str = None, error_message: str = None) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            updates = ["status = ?"]
            params = [status]
            if duration is not None:
                updates.append("duration = ?")
                params.append(duration)
            if local_audio_path is not None:
                updates.append("local_audio_path = ?")
                params.append(local_audio_path)
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            params.append(video_id)
            cursor.execute(f"UPDATE videos SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    def is_video_processed(self, video_id: str) -> bool:
        """Checks if a video has already been verified and analyzed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM videos WHERE id = ?", (video_id,))
            row = cursor.fetchone()
            if not row:
                return False
            return row["status"] in ("analyzed", "filtered_views", "filtered_date")

    # Transcription & Match operations
    def save_transcription(self, video_id: str, audio_type: str, full_text: str,
                           segments: List[Dict[str, Any]], language: str,
                           language_probability: float) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO transcriptions (video_id, audio_type, full_text, segments_json, language, language_probability, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (video_id, audio_type, full_text, json.dumps(segments, ensure_ascii=False),
                  language, language_probability, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid

    def save_match(self, video_id: str, variant: str, matched_phrase: str,
                   start_time: float, end_time: float, timecode_str: str,
                   confidence: float, method: str, full_transcription: str,
                   is_doubtful: bool = False, reprocessed_with_demucs: bool = False,
                   verification_notes: str = "") -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Remove any previous match for this video
            cursor.execute("DELETE FROM matches WHERE video_id = ?", (video_id,))
            cursor.execute("""
            INSERT INTO matches (video_id, variant, matched_phrase, start_time, end_time,
                                 timecode_str, confidence, method, full_transcription,
                                 is_doubtful, reprocessed_with_demucs, verification_notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (video_id, variant, matched_phrase, start_time, end_time,
                  timecode_str, confidence, method, full_transcription,
                  1 if is_doubtful else 0, 1 if reprocessed_with_demucs else 0,
                  verification_notes, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid

    def get_results_table_data(self, variant_filter: Optional[str] = None,
                               start_date: Optional[Union[date, datetime]] = None,
                               end_date: Optional[Union[date, datetime]] = None,
                               author: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns structured data for table display and export:
        Video | Views | Variant | Transcription | Timecode | Confidence
        Filtered strictly by date range (inclusive) and author if provided.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
            SELECT 
                v.id as video_id,
                v.url as video_url,
                v.author as author,
                v.views as views,
                v.upload_date as upload_date,
                v.upload_timestamp as upload_timestamp,
                v.duration as duration,
                v.status as video_status,
                v.error_message as error_message,
                m.variant as variant,
                m.matched_phrase as matched_phrase,
                m.timecode_str as timecode,
                m.start_time as start_time,
                m.end_time as end_time,
                m.confidence as confidence,
                m.method as method,
                m.is_doubtful as is_doubtful,
                m.reprocessed_with_demucs as reprocessed_with_demucs,
                COALESCE(m.full_transcription, (SELECT t.full_text FROM transcriptions t WHERE t.video_id = v.id ORDER BY t.id DESC LIMIT 1), '') as transcription
            FROM videos v
            LEFT JOIN matches m ON v.id = m.video_id
            WHERE 1=1
            """
            params = []
            if author and author.strip():
                clean_auth = author.strip().lstrip("@").lower()
                query += " AND LOWER(REPLACE(COALESCE(v.author, ''), '@', '')) = ?"
                params.append(clean_auth)

            if variant_filter:
                if variant_filter == "all_matches":
                    query += " AND m.variant IN ('variant_1', 'variant_2', 'variant_3')"
                elif variant_filter == "doubtful":
                    query += " AND m.is_doubtful = 1"
                elif variant_filter == "not_found":
                    query += " AND (m.variant = 'none' OR m.variant IS NULL) AND v.status = 'analyzed'"
                elif variant_filter == "poor_quality":
                    query += " AND v.status IN ('poor_quality', 'error')"
                elif variant_filter == "filtered_views":
                    query += " AND v.status = 'filtered_views'"
                elif variant_filter == "filtered_date":
                    query += " AND v.status = 'filtered_date'"
                elif variant_filter in ("variant_1", "variant_2", "variant_3"):
                    query += " AND m.variant = ?"
                    params.append(variant_filter)
                elif variant_filter == "all_collected":
                    pass  # Return all collected
            else:
                # Default: analyzed or errors
                query += " AND v.status IN ('analyzed', 'error', 'poor_quality')"
            
            query += " ORDER BY v.upload_timestamp DESC"
            cursor.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]

            if start_date is not None or end_date is not None:
                s_date = start_date.date() if isinstance(start_date, datetime) else start_date
                e_date = end_date.date() if isinstance(end_date, datetime) else end_date

                filtered_rows = []
                for r in rows:
                    u_ts = r.get("upload_timestamp")
                    if not u_ts:
                        u_str = r.get("upload_date")
                        if u_str and len(str(u_str)) >= 10:
                            try:
                                d_parsed = datetime.strptime(str(u_str)[:10], "%Y-%m-%d").date()
                                if (not s_date or d_parsed >= s_date) and (not e_date or d_parsed <= e_date):
                                    filtered_rows.append(r)
                            except Exception:
                                pass
                        continue

                    # Strictly inclusive date check against UTC publication timestamp
                    u_date = datetime.fromtimestamp(u_ts, tz=timezone.utc).date()
                    if s_date and u_date < s_date:
                        continue
                    if e_date and u_date > e_date:
                        continue
                    filtered_rows.append(r)
                return filtered_rows

            return rows

    def get_summary_stats(self, start_date: Optional[Union[date, datetime]] = None,
                          end_date: Optional[Union[date, datetime]] = None,
                          author: Optional[str] = None) -> Dict[str, int]:
        """Calculates counts for dashboard overview, optionally restricted to a date range and author."""
        all_collected = self.get_results_table_data("all_collected", start_date=start_date, end_date=end_date, author=author)
        return {
            "total_collected": len(all_collected),
            "total_views": sum(r.get("views", 0) for r in all_collected),
            "filtered_views_sum": sum(r.get("views", 0) for r in all_collected if r.get("video_status") == "filtered_views"),
            "promo_views_sum": sum(r.get("views", 0) for r in all_collected if r.get("variant") in ("variant_1", "variant_2", "variant_3") and r.get("video_status") == "analyzed"),
            "filtered_views": sum(1 for r in all_collected if r.get("video_status") == "filtered_views"),
            "filtered_date": sum(1 for r in all_collected if r.get("video_status") == "filtered_date"),
            "total_analyzed": sum(1 for r in all_collected if r.get("video_status") == "analyzed"),
            "variant_1": sum(1 for r in all_collected if r.get("variant") == "variant_1" and r.get("video_status") == "analyzed"),
            "variant_2": sum(1 for r in all_collected if r.get("variant") == "variant_2" and r.get("video_status") == "analyzed"),
            "variant_3": sum(1 for r in all_collected if r.get("variant") == "variant_3" and r.get("video_status") == "analyzed"),
            "not_found": sum(1 for r in all_collected if r.get("video_status") == "analyzed" and r.get("variant") in ("none", None)),
            "poor_quality": sum(1 for r in all_collected if r.get("video_status") in ("poor_quality", "error")),
            "doubtful": sum(1 for r in all_collected if r.get("is_doubtful") and r.get("video_status") == "analyzed")
        }

    def get_all_videos_data(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all collected videos regardless of analysis status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
            SELECT 
                v.id as video_id,
                v.url as video_url,
                v.author as author,
                v.title as title,
                v.views as views,
                v.upload_date as upload_date,
                v.duration as duration,
                v.status as video_status,
                v.error_message as error_message,
                m.variant as variant,
                m.matched_phrase as matched_phrase,
                m.timecode_str as timecode,
                m.confidence as confidence,
                m.method as method,
                m.is_doubtful as is_doubtful,
                COALESCE(m.full_transcription, (SELECT t.full_text FROM transcriptions t WHERE t.video_id = v.id ORDER BY t.id DESC LIMIT 1), '') as transcription
            FROM videos v
            LEFT JOIN matches m ON v.id = m.video_id
            """
            params = []
            if status_filter:
                query += " WHERE v.status = ?"
                params.append(status_filter)
            
            query += " ORDER BY v.upload_timestamp DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def clear_database(self, only_test_data: bool = False) -> None:
        """Clears scan history and video data, then runs VACUUM to reclaim disk space."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if only_test_data:
                cursor.execute("DELETE FROM matches WHERE video_id LIKE '7429%'")
                cursor.execute("DELETE FROM transcriptions WHERE video_id LIKE '7429%'")
                cursor.execute("DELETE FROM videos WHERE id LIKE '7429%'")
            else:
                cursor.execute("DELETE FROM matches")
                cursor.execute("DELETE FROM transcriptions")
                cursor.execute("DELETE FROM videos")
                cursor.execute("DELETE FROM scans")
            conn.commit()

        # Run VACUUM outside the write transaction to shrink file on disk
        try:
            raw_conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            raw_conn.execute("VACUUM;")
            raw_conn.close()
        except Exception:
            pass

