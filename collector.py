"""TikTok post collection and filtering module.

Handles:
- Public post scraping via tt-dlp / mirror resolver
- View count filtering (> 2000)
- Publication date range filtering (inclusive)
- Duplicate checking against database
- Manual URL/file import fallbacks if TikTok WAF/CAPTCHA triggers
"""

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

import yt_dlp
from curl_cffi import requests as c_req

from database import Database

logger = logging.getLogger(__name__)


class TikTokCollector:
    def __init__(self, db: Database, cookies_file: Optional[str] = None):
        self.db = db
        self.cookies_file = cookies_file

    @staticmethod
    def parse_tiktok_id_from_url(url: str) -> Optional[str]:
        """Extracts the numeric video ID from various TikTok URL patterns."""
        match = re.search(r"/video/(\d+)", url)
        if match:
            return match.group(1)
        match = re.search(r"/v/(\d+)", url)
        if match:
            return match.group(1)
        match = re.search(r"(\d{15,22})", url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def extract_username(url_or_name: str) -> str:
        """Extracts clean lowercase username from TikTok URL or handle."""
        if not url_or_name:
            return ""
        s = url_or_name.strip()
        m = re.search(r"@([a-zA-Z0-9_\.]+)", s)
        if m:
            return m.group(1).lstrip("@").lower()
        m2 = re.search(r"tiktok\.com/([a-zA-Z0-9_\.]+)", s)
        if m2:
            return m2.group(1).lstrip("@").lower()
        clean = s.split("?")[0].split("/")[0].lstrip("@").lower()
        return clean

    @staticmethod
    def extract_snowflake_timestamp(video_id: str) -> Optional[int]:
        """Extracts the exact Unix timestamp in seconds from a TikTok Snowflake ID.
        In TikTok's 64-bit ID architecture, bits 32-63 represent the Unix epoch timestamp.
        """
        try:
            vid_int = int(video_id)
            if vid_int > 10**16:
                ts = vid_int >> 32
                if 1400000000 < ts < 2500000000:
                    return ts
        except Exception:
            pass
        return None

    @staticmethod
    def is_within_date_range(upload_dt: Optional[datetime],
                             start_date: Optional[Any],
                             end_date: Optional[Any]) -> bool:
        """Checks if upload_dt falls within [start_date, end_date] inclusive.
        Uses UTC calendar date of the video timestamp for deterministic, exact date matching.
        """
        if start_date is None and end_date is None:
            return True
        if upload_dt is None:
            return False  # Strict: cannot pass date filter if date is unknown

        s_date = start_date.date() if isinstance(start_date, datetime) else start_date
        e_date = end_date.date() if isinstance(end_date, datetime) else end_date

        u_date = upload_dt.astimezone(timezone.utc).date() if upload_dt.tzinfo else upload_dt.date()

        if s_date and u_date < s_date:
            return False
        if e_date and u_date > e_date:
            return False
        return True

    @staticmethod
    def parse_views_str(v_str: str) -> int:
        """Parses human view strings like '137', '1.87K', '59.5K', '1.2M'."""
        v_str = str(v_str).strip().upper()
        if not v_str:
            return 0
        mult = 1
        if v_str.endswith('K'):
            mult = 1_000
            v_str = v_str[:-1]
        elif v_str.endswith('M'):
            mult = 1_000_000
            v_str = v_str[:-1]
        elif v_str.endswith('B'):
            mult = 1_000_000_000
            v_str = v_str[:-1]
        try:
            return int(float(v_str.replace(',', '')) * mult)
        except ValueError:
            return 0

    @staticmethod
    def parse_relative_time_str(time_str: str) -> datetime:
        """Parses strings like '11 minutes ago', '5 hours ago', '3 days ago'."""
        now = datetime.now(timezone.utc)
        time_str = str(time_str).lower().strip()
        m = re.search(r'(\d+)\s*(minute|min|hour|hr|day|week|month|year)', time_str)
        if m:
            val = int(m.group(1))
            unit = m.group(2)
            if 'min' in unit:
                return now - timedelta(minutes=val)
            elif 'hour' in unit or 'hr' in unit:
                return now - timedelta(hours=val)
            elif 'day' in unit:
                return now - timedelta(days=val)
            elif 'week' in unit:
                return now - timedelta(weeks=val)
            elif 'month' in unit:
                return now - timedelta(days=val * 30)
            elif 'year' in unit:
                return now - timedelta(days=val * 365)
        # Attempt YYYY-MM-DD parse
        m_date = re.search(r'(\d{4})-(\d{2})-(\d{2})', time_str)
        if m_date:
            try:
                return datetime.strptime(m_date.group(0), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                pass
        return now

    @classmethod
    def extract_cards_from_html(cls, html_content: str, clean_user: str) -> List[Dict[str, Any]]:
        """Extracts structured card info (id, views, upload_date, title) from HTML."""
        cards = []
        blocks = html_content.split('<div class="thumb')
        for b in blocks[1:]:
            vid_m = re.search(r'href="https://urlebird\.com/video/(?:[^\"]*?-)?(\d{18,20})/?["\']', b)
            if not vid_m:
                vid_m = re.search(r'/video/[^"]*?(\d{18,20})', b)
            if not vid_m:
                continue
            vid_id = vid_m.group(1)

            views_m = re.search(r'fa-play"[^>]*></i>\s*([0-9\.,KMBkmb]+)', b)
            views = cls.parse_views_str(views_m.group(1)) if views_m else 0

            # Primary: Extract exact second from TikTok 64-bit Snowflake ID
            ts = cls.extract_snowflake_timestamp(vid_id)
            if ts:
                upload_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                clock_m = re.search(r'fa-clock"[^>]*></i>\s*([^<]+)', b)
                clock_raw = clock_m.group(1).strip() if clock_m else ""
                upload_dt = cls.parse_relative_time_str(clock_raw)
                ts = int(upload_dt.timestamp())

            desc_m = re.search(r'<div class="info3">.*?<span>([^<]*)</span>', b, re.DOTALL)
            desc = desc_m.group(1).strip() if desc_m else ""

            cards.append({
                "id": vid_id,
                "url": f"https://www.tiktok.com/@{clean_user}/video/{vid_id}",
                "author": clean_user,
                "title": desc,
                "views": views,
                "upload_date": upload_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "upload_timestamp": ts
            })
        return cards

    def build_ydl_options(self, extract_flat: bool = True) -> Dict[str, Any]:
        """Configures yt-dlp options respecting TikTok terms."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
            "extract_flat": "in_playlist" if extract_flat else False,
        }
        if self.cookies_file and Path(self.cookies_file).exists():
            opts["cookiefile"] = self.cookies_file
        return opts

    def collect_from_channel(self, channel_url: str,
                             start_date: Optional[datetime] = None,
                             end_date: Optional[datetime] = None,
                             min_views: int = 2000,
                             progress_callback: Optional[Callable[[str, int, int], None]] = None
                             ) -> Dict[str, Any]:
        """Collects public posts from a TikTok channel URL using multi-stage strategy."""
        result = {
            "success": False,
            "total_found": 0,
            "passed_filter": [],
            "filtered_views_count": 0,
            "filtered_date_count": 0,
            "error_message": None,
            "waf_blocked": False
        }

        # Step 1: Extract username
        username = self.extract_username(channel_url)
        if not username:
            username = "unknown"

        # Step 2: Try authenticated tt-dlp client if cookies provided
        if self.cookies_file and Path(self.cookies_file).exists():
            try:
                from tt_dlp.client import TikTokClient as TtClient
                from tt_dlp.models import Settings as TtSettings
                if progress_callback:
                    progress_callback(f"Попытка сбора публикаций через tt-dlp с cookies...", 0, 1)
                tt_settings = TtSettings(
                    output=Path("data/downloads"),
                    cookies=Path(self.cookies_file),
                    profile_store=None,
                    limit=200,
                    sleep=1.0,
                    overwrite=False,
                    dry_run=True,
                    stories=False,
                    identify=False
                )
                tt_client = TtClient(tt_settings)
                identity = tt_client.authenticated_profile_identity(username)
                if identity and identity.sec_uid:
                    items = tt_client.collect_posts(identity.sec_uid, profile_url=f"https://www.tiktok.com/@{username}")
                    if items:
                        logger.info("Collected %d items via authenticated tt-dlp", len(items))
                        urls = [f"https://www.tiktok.com/@{username}/video/{it.post_id}" for it in items]
                        return self.collect_from_urls(urls, start_date=start_date, end_date=end_date,
                                                      min_views=min_views, progress_callback=progress_callback)
            except Exception as e:
                logger.warning("tt-dlp authenticated collection fallback: %s", e)

        # Step 3: Fast multi-page public resolution (fully automated, no WAF challenge)
        if progress_callback:
            progress_callback(f"Поиск публикаций @{username} на открытом шлюзе...", 0, 1)

        mirror_res = self.collect_from_public_mirror(
            username=username,
            start_date=start_date,
            end_date=end_date,
            min_views=min_views,
            progress_callback=progress_callback
        )
        if mirror_res and mirror_res.get("success") and (mirror_res.get("total_found", 0) > 0):
            logger.info("Successfully collected %d videos via mirror for @%s", mirror_res["total_found"], username)
            return mirror_res

        # Step 4: Fallback to direct yt-dlp
        ydl_opts = self.build_ydl_options(extract_flat=True)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                if info and "entries" in info and info["entries"]:
                    entries = [e for e in info.get("entries", []) if e]
                    result["total_found"] = len(entries)
                    for idx, entry in enumerate(entries):
                        if progress_callback:
                            progress_callback(f"Анализ видео {idx+1}/{len(entries)}...", idx+1, len(entries))
                        video_info = self._process_entry(entry, start_date, end_date, min_views, result, target_user=username)
                        if video_info:
                            result["passed_filter"].append(video_info)
                    result["success"] = True
                    return result
        except Exception as e:
            logger.warning("Direct yt-dlp extraction failed: %s", e)

        result["error_message"] = (
            "Не удалось автоматически извлечь публикации профиля TikTok. "
            "TikTok применил защитный экран. "
            "Вы можете вставить ссылки на видео вручную в поле слева или использовать cookies.txt."
        )
        result["waf_blocked"] = True
        return result

    def collect_from_public_mirror(self, username: str,
                                   start_date: Optional[datetime] = None,
                                   end_date: Optional[datetime] = None,
                                   min_views: int = 2000,
                                   max_pages: int = 20,
                                   progress_callback: Optional[Callable[[str, int, int], None]] = None
                                   ) -> Dict[str, Any]:
        """Collects video items with multi-page AJAX pagination and instant filtering."""
        clean_user = username.lstrip("@").strip()
        mirror_url = f"https://urlebird.com/user/{clean_user}/"

        if start_date and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        
        result = {
            "success": True,
            "total_found": 0,
            "passed_filter": [],
            "filtered_views_count": 0,
            "filtered_date_count": 0,
            "error_message": None,
            "waf_blocked": False
        }

        all_cards: List[Dict[str, Any]] = []
        seen_ids = set()

        try:
            r = c_req.get(mirror_url, impersonate="chrome124", timeout=15)
            if r.status_code == 200:
                p1_cards = self.extract_cards_from_html(r.text, clean_user)
                for c in p1_cards:
                    if c["id"] not in seen_ids:
                        seen_ids.add(c["id"])
                        all_cards.append(c)

                # Multi-page AJAX pagination
                btn_match = re.search(r'<button[^>]+id="load_more"[^>]*>', r.text)
                if btn_match:
                    btn_html = btn_match.group(0)
                    user_id_m = re.search(r'data-user-id="([^"]+)"', btn_html)
                    sec_uid_m = re.search(r'data-sec-uid="([^"]+)"', btn_html)
                    cursor_m = re.search(r'data-cursor="([^"]+)"', btn_html)
                    x_m = re.search(r'data-x="([^"]+)"', btn_html)

                    if user_id_m and sec_uid_m and cursor_m and x_m:
                        user_id = user_id_m.group(1)
                        sec_uid = sec_uid_m.group(1)
                        cursor = cursor_m.group(1)
                        x = x_m.group(1)

                        for page_num in range(2, max_pages + 1):
                            if progress_callback:
                                progress_callback(f"Загрузка страницы {page_num}... Собрано {len(all_cards)} видео", page_num, max_pages)

                            payload = {
                                'action': 'user',
                                'data': json.dumps({
                                    'user_id': user_id,
                                    'sec_uid': sec_uid,
                                    'cursor': cursor,
                                    'lang': '',
                                    'page': str(page_num),
                                    'x': x
                                })
                            }
                            ajax_headers = {
                                'Referer': mirror_url,
                                'X-Requested-With': 'XMLHttpRequest'
                            }
                            r_ajax = c_req.post('https://urlebird.com/ajax/', data=payload, headers=ajax_headers, impersonate='chrome124', timeout=15)
                            if r_ajax.status_code == 200 and r_ajax.text.startswith('{'):
                                data = r_ajax.json()
                                thumbs = data.get('thumbs', '')
                                if not thumbs:
                                    break
                                
                                # Robust cursor & state update from JSON response
                                cursor = data.get('cursor', cursor)
                                x = data.get('x', x)
                                user_id = data.get('u', user_id)
                                sec_uid = data.get('s', sec_uid)
                                has_more = data.get('has_more', False)

                                p_cards = self.extract_cards_from_html(thumbs, clean_user)
                                new_cards = [c for c in p_cards if c["id"] not in seen_ids]
                                for c in new_cards:
                                    seen_ids.add(c["id"])
                                all_cards.extend(new_cards)

                                # If start_date is specified, check if reached older videos (safe against pinned posts)
                                if start_date and new_cards:
                                    s_d = start_date.date() if isinstance(start_date, datetime) else start_date
                                    older_count = sum(1 for c in new_cards if datetime.fromtimestamp(c["upload_timestamp"], tz=timezone.utc).date() < s_d)
                                    if older_count >= max(1, int(len(new_cards) * 0.6)):
                                        logger.info("Reached video timestamps older than start_date (%s); stopping pagination.", s_d)
                                        break

                                if not has_more or not new_cards:
                                    break
        except Exception as e:
            logger.warning("Public mirror request failed: %s", e)

        if not all_cards:
            return {"success": False, "total_found": 0, "passed_filter": []}

        result["total_found"] = len(all_cards)

        # Process and filter all discovered cards
        for idx, card in enumerate(all_cards):
            video_id = card["id"]
            url = card["url"]
            author = card["author"]
            title = card["title"]
            views = card["views"]
            upload_dt = datetime.fromtimestamp(card["upload_timestamp"], tz=timezone.utc)
            upload_date_str = card["upload_date"]
            timestamp = card["upload_timestamp"]

            # Filter 1: Date range
            if not self.is_within_date_range(upload_dt, start_date, end_date):
                result["filtered_date_count"] += 1
                self.db.save_video(
                    video_id=video_id,
                    url=url,
                    author=author,
                    title=title,
                    views=views,
                    upload_date=upload_date_str,
                    upload_timestamp=timestamp,
                    status="filtered_date"
                )
                continue

            # Filter 2: Strictly > 2000 views
            if views <= min_views:
                result["filtered_views_count"] += 1
                self.db.save_video(
                    video_id=video_id,
                    url=url,
                    author=author,
                    title=title,
                    views=views,
                    upload_date=upload_date_str,
                    upload_timestamp=timestamp,
                    status="filtered_views"
                )
                continue

            # Check existing status in DB to preserve 'analyzed' videos
            existing = self.db.get_video(video_id)
            if existing and existing.get("status") == "analyzed":
                # Already analyzed previously! Keep status, but update views
                self.db.save_video(
                    video_id=video_id,
                    url=url,
                    author=author,
                    title=title,
                    views=views,
                    upload_date=upload_date_str,
                    upload_timestamp=timestamp,
                    status="analyzed"
                )
            else:
                self.db.save_video(
                    video_id=video_id,
                    url=url,
                    author=author,
                    title=title,
                    views=views,
                    upload_date=upload_date_str,
                    upload_timestamp=timestamp,
                    status="pending"
                )

            result["passed_filter"].append({
                "id": video_id,
                "url": url,
                "author": author,
                "title": title,
                "views": views,
                "upload_date": upload_date_str,
                "upload_timestamp": timestamp,
                "duration": 0
            })

        return result

    def collect_from_urls(self, urls: List[str],
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None,
                          min_views: int = 2000,
                          progress_callback: Optional[Callable[[str, int, int], None]] = None
                          ) -> Dict[str, Any]:
        """Processes an explicit list of TikTok video URLs."""
        result = {
            "success": True,
            "total_found": len(urls),
            "passed_filter": [],
            "filtered_views_count": 0,
            "filtered_date_count": 0,
            "error_message": None,
            "waf_blocked": False
        }

        ydl_opts = self.build_ydl_options(extract_flat=False)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for idx, raw_url in enumerate(urls):
                url = raw_url.strip()
                if not url:
                    continue

                if progress_callback:
                    progress_callback(f"Получение информации о видео {idx+1}/{len(urls)}...", idx+1, len(urls))

                try:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        continue
                    u_target = self.extract_username(url)
                    video_info = self._process_entry(info, start_date, end_date, min_views, result, target_user=u_target)
                    if video_info:
                        result["passed_filter"].append(video_info)
                except Exception as e:
                    logger.warning("Could not fetch info for %s: %s", url, e)
                    vid_id = self.parse_tiktok_id_from_url(url)
                    u_target = self.extract_username(url) or "unknown"
                    if vid_id:
                        self.db.save_video(
                            video_id=vid_id,
                            url=url,
                            author=u_target,
                            title="",
                            views=0,
                            upload_date="",
                            upload_timestamp=0,
                            status="error",
                            error_message=f"Ошибка загрузки метаданных: {e}"
                        )

        return result

    def _process_entry(self, entry: Dict[str, Any],
                       start_date: Optional[datetime],
                       end_date: Optional[datetime],
                       min_views: int,
                       stats: Dict[str, Any],
                       target_user: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parses a single video entry, applies view and date filters, and records in SQLite."""
        video_id = str(entry.get("id") or self.parse_tiktok_id_from_url(entry.get("url") or ""))
        url = entry.get("webpage_url") or entry.get("url")
        if not url and video_id:
            raw_uploader = target_user or entry.get("uploader") or entry.get("channel") or "video"
            clean_uploader = self.extract_username(str(raw_uploader)) or "video"
            url = f"https://www.tiktok.com/@{clean_uploader}/video/{video_id}"

        if not video_id or not url:
            return None

        views = entry.get("view_count")
        if views is None:
            views = entry.get("play_count") or 0
        views = int(views)

        # Resolve timestamp: 1) Snowflake ID, 2) entry timestamp/create_time, 3) upload_date string
        ts = self.extract_snowflake_timestamp(video_id)
        if not ts:
            ts = entry.get("timestamp") or entry.get("create_time")

        upload_dt = None
        if ts:
            try:
                ts = int(ts)
                upload_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                pass

        if not upload_dt:
            upload_date_str = entry.get("upload_date")  # YYYYMMDD
            if upload_date_str and len(str(upload_date_str)) == 8:
                try:
                    upload_dt = datetime.strptime(str(upload_date_str), "%Y%m%d").replace(tzinfo=timezone.utc)
                    ts = int(upload_dt.timestamp())
                except Exception:
                    pass

        timestamp = ts or 0
        upload_date_formatted = upload_dt.strftime("%Y-%m-%d %H:%M:%S") if upload_dt else ""

        raw_author = target_user or entry.get("uploader") or entry.get("channel") or self.extract_username(url) or "unknown"
        author = self.extract_username(str(raw_author)) or "unknown"
        title = entry.get("title") or entry.get("description") or ""

        # Filter 1: Date range filter
        if not self.is_within_date_range(upload_dt, start_date, end_date):
            stats["filtered_date_count"] += 1
            self.db.save_video(
                video_id=video_id,
                url=url,
                author=author,
                title=title,
                views=views,
                upload_date=upload_date_formatted,
                upload_timestamp=timestamp,
                status="filtered_date"
            )
            return None

        # Filter 2: Strictly > 2000 views
        if views <= min_views:
            stats["filtered_views_count"] += 1
            self.db.save_video(
                video_id=video_id,
                url=url,
                author=author,
                title=title,
                views=views,
                upload_date=upload_dt.strftime("%Y-%m-%d %H:%M:%S"),
                upload_timestamp=timestamp,
                status="filtered_views"
            )
            return None

        # Video passed both filters!
        existing = self.db.get_video(video_id)
        if not (existing and existing.get("status") == "analyzed"):
            self.db.save_video(
                video_id=video_id,
                url=url,
                author=author,
                title=title,
                views=views,
                upload_date=upload_dt.strftime("%Y-%m-%d %H:%M:%S"),
                upload_timestamp=timestamp,
                status="pending"
            )

        return {
            "id": video_id,
            "url": url,
            "author": author,
            "title": title,
            "views": views,
            "upload_date": upload_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "upload_timestamp": timestamp,
            "duration": entry.get("duration") or 0
        }
