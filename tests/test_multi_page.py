from curl_cffi import requests
import json
import re

def scrape_twitch_clown_videos(max_pages=3):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    }
    r = requests.get('https://urlebird.com/user/twitch.clown/', headers=headers, impersonate='chrome124', timeout=12)
    if r.status_code != 200:
        return []

    video_ids = []
    seen = set()

    # Page 1 links
    links_p1 = re.findall(r'href="https://urlebird\.com/video/([^"]+)"', r.text)
    for l in links_p1:
        m = re.search(r'(\d{18,20})', l)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            video_ids.append(m.group(1))
    print(f"Page 1: {len(seen)} videos")

    # Pagination via AJAX
    btn_match = re.search(r'<button[^>]+id="load_more"[^>]*>', r.text)
    if not btn_match:
        return video_ids

    btn_html = btn_match.group(0)
    user_id_m = re.search(r'data-user-id="([^"]+)"', btn_html)
    sec_uid_m = re.search(r'data-sec-uid="([^"]+)"', btn_html)
    cursor_m = re.search(r'data-cursor="([^"]+)"', btn_html)
    x_m = re.search(r'data-x="([^"]+)"', btn_html)

    if not (user_id_m and sec_uid_m and cursor_m and x_m):
        return video_ids

    user_id = user_id_m.group(1)
    sec_uid = sec_uid_m.group(1)
    cursor = cursor_m.group(1)
    x = x_m.group(1)

    for p in range(2, max_pages + 1):
        payload = {
            'action': 'user',
            'data': json.dumps({
                'user_id': user_id,
                'sec_uid': sec_uid,
                'cursor': cursor,
                'lang': '',
                'page': str(p),
                'x': x
            })
        }
        ajax_headers = {
            'Referer': 'https://urlebird.com/user/twitch.clown/',
            'X-Requested-With': 'XMLHttpRequest'
        }
        r_ajax = requests.post('https://urlebird.com/ajax/', data=payload, headers=ajax_headers, impersonate='chrome124', timeout=12)
        if r_ajax.status_code != 200 or not r_ajax.text.startswith('{'):
            break

        data = r_ajax.json()
        thumbs = data.get('thumbs', '')
        if not thumbs:
            break

        new_count = 0
        ajax_ids = re.findall(r'(\d{18,20})', thumbs)
        for vid in ajax_ids:
            if vid not in seen:
                seen.add(vid)
                video_ids.append(vid)
                new_count += 1
        print(f"Page {p}: +{new_count} videos (total: {len(video_ids)})")

        # Update cursor from response if present
        cur_m = re.search(r'data-cursor="([^"]+)"', thumbs)
        if cur_m:
            cursor = cur_m.group(1)
        x_new_m = re.search(r'data-x="([^"]+)"', thumbs)
        if x_new_m:
            x = x_new_m.group(1)

        if new_count == 0:
            break

    return video_ids

v_list = scrape_twitch_clown_videos(max_pages=3)
print(f"Total videos gathered: {len(v_list)}")
