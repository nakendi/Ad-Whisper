from curl_cffi import requests
import re

all_ids = []
seen = set()

for page in range(1, 4):
    url = f"https://urlebird.com/user/twitch.clown/?page={page}"
    r = requests.get(url, impersonate="chrome124", timeout=12)
    links = re.findall(r'href="https://urlebird\.com/video/([^"]+)"', r.text)
    page_count = 0
    for l in links:
        m = re.search(r'(\d{18,20})', l)
        if m:
            vid_id = m.group(1)
            if vid_id not in seen:
                seen.add(vid_id)
                all_ids.append(vid_id)
                page_count += 1
    print(f"Page {page}: found {page_count} new videos, total: {len(all_ids)}")

print(f"Total collected {len(all_ids)} video IDs for @twitch.clown!")
for i, v in enumerate(all_ids[:5], 1):
    print(f"{i}. https://www.tiktok.com/@twitch.clown/video/{v}")
