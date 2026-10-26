from curl_cffi import requests as c_req
import re
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}

# 1. Test Urlebird
try:
    r = c_req.get('https://urlebird.com/user/twitch.clown/', headers=headers, impersonate='chrome124', timeout=10)
    print('Urlebird status:', r.status_code)
    # Find tiktok video IDs or links
    # URLs typically like /video/twitch-clown-7345678.../ or similar
    matches = re.findall(r'/video/([^"\'\s>]+)', r.text)
    print('Urlebird matches count:', len(matches))
    for m in matches[:5]:
        # Extract numeric id
        num_m = re.search(r'(\d{15,22})', m)
        if num_m:
            print('Found video ID:', num_m.group(1))
except Exception as e:
    print('Urlebird error:', e)

# 2. Test Tokcounter / other mirrors
try:
    r2 = c_req.get('https://tokcounter.com/user/twitch.clown', headers=headers, impersonate='chrome124', timeout=10)
    print('Tokcounter status:', r2.status_code)
except Exception as e:
    print('Tokcounter error:', e)

# 3. Test Google Search for site:tiktok.com/@twitch.clown/video/
try:
    g_url = 'https://html.duckduckgo.com/html/?q=site:tiktok.com/@twitch.clown/video/'
    rg = c_req.get(g_url, headers=headers, impersonate='chrome124', timeout=10)
    print('DDG status:', rg.status_code)
    ddg_links = re.findall(r'(https://www\.tiktok\.com/@twitch\.clown/video/\d+)', rg.text)
    print('DDG links found:', len(ddg_links), set(ddg_links))
except Exception as e:
    print('DDG error:', e)
