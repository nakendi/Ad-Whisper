from curl_cffi import requests
import json
import re

r1 = requests.get('https://urlebird.com/user/twitch.clown/', impersonate='chrome124')
btn_match = re.search(r'<button[^>]+id="load_more"[^>]*>', r1.text)
if btn_match:
    btn_html = btn_match.group(0)
    user_id = re.search(r'data-user-id="([^"]+)"', btn_html).group(1)
    sec_uid = re.search(r'data-sec-uid="([^"]+)"', btn_html).group(1)
    cursor = re.search(r'data-cursor="([^"]+)"', btn_html).group(1)
    x = re.search(r'data-x="([^"]+)"', btn_html).group(1)

    payload = {
        'action': 'user',
        'data': json.dumps({
            'user_id': user_id,
            'sec_uid': sec_uid,
            'cursor': cursor,
            'lang': '',
            'page': '2',
            'x': x
        })
    }
    r2 = requests.post('https://urlebird.com/ajax/', data=payload, headers={'Referer': 'https://urlebird.com/user/twitch.clown/', 'X-Requested-With': 'XMLHttpRequest'}, impersonate='chrome124')
    data = r2.json()
    thumbs_html = data.get('thumbs', '')
    print('Thumbs HTML length:', len(thumbs_html))
    
    # Extract IDs: URLs in thumbs are like https://urlebird.com/video/...-7700.../
    found_ids = set(re.findall(r'(\d{18,20})', thumbs_html))
    print('Found video IDs in page 2:', len(found_ids))
    print('IDs:', list(found_ids)[:5])
