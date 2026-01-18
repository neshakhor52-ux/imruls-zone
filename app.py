from flask import Flask, request, jsonify, render_template
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from urllib.parse import urlparse
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

start_time = datetime.now()

ALLOWED_DOMAINS = ['www.facebook.com', 'm.facebook.com', 'facebook.com']
REQUEST_TIMEOUT = 30
MAX_RETRIES = 2


class FacebookProfileScraper:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Dnt': '1'
        }

    def validate_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ['http', 'https']:
                return False
            if parsed.netloc not in ALLOWED_DOMAINS:
                return False
            if any(c in url for c in ['<', '>', '"', "'"]):
                return False
            return True
        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False

    def initialize_session(self) -> bool:
        try:
            init_url = 'https://www.facebook.com/'
            r = self.session.get(init_url, headers=self.headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Session initialization error: {e}")
            return False

    def normalize_profile_url(self, url: str):
        if not self.validate_url(url):
            return None

        # resolve share links
        if '/share/' in url:
            try:
                r = self.session.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                url = r.url
            except Exception as e:
                logger.error(f"Failed to resolve share link: {e}")
                return None

        if 'm.facebook.com' in url:
            url = url.replace('m.facebook.com', 'www.facebook.com')
        elif 'facebook.com' in url and 'www.' not in url:
            url = url.replace('facebook.com', 'www.facebook.com')

        parsed = urlparse(url)
        if parsed.netloc not in ALLOWED_DOMAINS:
            return None
        return url

    def is_valid_image_url(self, url: str) -> bool:
        if not url or not isinstance(url, str):
            return False
        if len(url) > 2000:
            return False

        invalid_extensions = ['.js', '.css', '.ico', '.json', '.xml', '.txt', '.html']
        for ext in invalid_extensions:
            if url.lower().endswith(ext):
                return False

        image_indicators = [
            '.jpg', '.jpeg', '.png', '.webp', '.gif',
            'photo', 'picture', 'image', '/t39.', '/t1.',
            'fbcdn.net', 'scontent'
        ]
        return any(ind in url.lower() for ind in image_indicators)

    def clean_url(self, url: str) -> str:
        url = url.replace('&amp;', '&')
        url = url.replace('&lt;', '<').replace('&gt;', '>')
        url = url.replace('&quot;', '"')
        url = url.replace('&#039;', "'")
        url = url.replace('\\/', '/')
        url = url.replace('\\"', '"')
        return url.strip()

    def sanitize_url(self, url: str) -> str:
        url = self.clean_url(url)
        url = url.split('"')[0].split("'")[0].split('>')[0].split('<')[0]
        url = url.split('\\')[0]
        return url.strip()

    def get_profile_page(self, profile_url: str):
        normalized_url = self.normalize_profile_url(profile_url)
        if not normalized_url:
            return None

        self.headers['Referer'] = 'https://www.facebook.com/'

        for attempt in range(MAX_RETRIES):
            try:
                r = self.session.get(
                    normalized_url,
                    headers=self.headers,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True
                )
                if r.status_code == 200:
                    return r.text
                if r.status_code == 429:
                    logger.warning(f"Rate limited on attempt {attempt + 1}")
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"HTTP {r.status_code} on attempt {attempt + 1}")
            except requests.exceptions.Timeout:
                logger.error(f"Timeout on attempt {attempt + 1}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Fetch error: {e}")

        return None

    def get_image_size_score(self, url: str) -> int:
        # prefers bigger sizes when encoded in url
        patterns = [
            (r's(\d+)x(\d+)', 1),
            (r'p(\d+)x(\d+)', 1),
            (r'ctp=s(\d+)x(\d+)', 1)
        ]
        for pat, group in patterns:
            m = re.search(pat, url)
            if m:
                return int(m.group(group))

        for v in [40, 160, 320, 480, 720, 960]:
            if f's{v}x{v}' in url:
                return v

        if '?' not in url or 'stp=' not in url:
            return 9999
        return 500

    def extract_image_id(self, url: str):
        m = re.search(r'/(\d+)_(\d+)_(\d+)_[on]\.jpg', url)
        return m.group(2) if m else None

    def extract_image_urls(self, html_content: str):
        soup = BeautifulSoup(html_content, 'html.parser')

        images = {
            'profile_picture': None,
            'profile_picture_hd': None,
            'cover_photo': None,
            'cover_photo_hd': None,
            'photo_images': [],
            'all_images': set()
        }

        # collect from img tags
        for img in soup.find_all('img', limit=500):
            src = img.get('src', '')
            if src and self.is_valid_image_url(src):
                src = self.sanitize_url(src)
                if src and len(src) < 2000:
                    images['all_images'].add(src)

        page_text = str(soup)

        patterns = [
            r'https://scontent[^"\'\\<>\s]+\\.fbcdn\\.net[^"\'\\<>\s]+\\.(?:jpg|jpeg|png|webp)[^"\'\\<>\s]*',
            r'"(https://scontent[^"]+\\.fbcdn\\.net[^"]+\\.(?:jpg|jpeg|png|webp)[^"]*)"'
        ]

        for pat in patterns:
            for u in re.findall(pat, page_text, re.IGNORECASE):
                if isinstance(u, tuple):
                    u = u[0] if u else ''
                u = self.sanitize_url(u)
                if u and self.is_valid_image_url(u) and len(u) < 2000 and 'fbcdn.net' in u:
                    images['all_images'].add(u)

        profile_variants = {}
        cover_variants = {}
        photo_candidates = []

        for img_url in images['all_images']:
            img_id = self.extract_image_id(img_url)
            is_profile_type = '/t39.30808-1/' in img_url or '3ab345' in img_url or '1d2534' in img_url
            is_cover_type = '/t39.30808-6/' in img_url
            size_score = self.get_image_size_score(img_url)

            if is_profile_type and img_id:
                profile_variants.setdefault(img_id, []).append((size_score, img_url))

            if is_cover_type and img_id:
                cover_variants.setdefault(img_id, []).append((size_score, img_url))

            if is_cover_type and size_score >= 320:
                photo_candidates.append((size_score, img_url))

        if profile_variants:
            best_id = max(profile_variants.keys(), key=lambda k: max(v[0] for v in profile_variants[k]))
            versions = sorted(profile_variants[best_id], key=lambda x: x[0], reverse=True)
            images['profile_picture_hd'] = versions[0][1]
            images['profile_picture'] = versions[0][1]

        if cover_variants:
            best_id = max(cover_variants.keys(), key=lambda k: max(v[0] for v in cover_variants[k]))
            versions = sorted(cover_variants[best_id], key=lambda x: x[0], reverse=True)
            images['cover_photo_hd'] = versions[0][1]
            images['cover_photo'] = versions[0][1]

        photo_candidates.sort(reverse=True, key=lambda x: x[0])
        seen_ids = set()
        unique = []
        for score, u in photo_candidates:
            img_id = self.extract_image_id(u)
            if img_id and img_id not in seen_ids:
                seen_ids.add(img_id)
                unique.append(u)
                if len(unique) >= 10:
                    break

        images['photo_images'] = unique
        images['all_images'] = list(images['all_images'])
        return images

    def scrape_profile(self, profile_url: str):
        if not self.validate_url(profile_url):
            logger.error(f"Invalid URL provided: {profile_url}")
            return None

        if not self.initialize_session():
            return None

        html = self.get_profile_page(profile_url)
        if not html:
            return None

        return self.extract_image_urls(html)


@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')


@app.route('/api', methods=['GET'])
def welcome():
    return jsonify({
        "message": "Facebook Profile Scraper API",
        "description": "Extract profile pictures, cover photos, and other images from Facebook profiles",
        "warning": "Educational use only. Scraping Facebook may violate their Terms of Service.",
        "endpoint": "/api/all",
        "usage": "/api/all?url=https://www.facebook.com/username",
        "parameters": {"url": "Facebook profile URL (required)"},
        "example": "/api/all?url=https://www.facebook.com/share/1BsGawqkh/",
        "developer": "@imrulbhai69",
        "version": "2.3.0",
        "uptime": str(datetime.now() - start_time)
    })


@app.route('/api/all', methods=['GET'])
def get_all_images():
    request_start = time.time()

    profile_url = request.args.get('url', '').strip()

    if not profile_url:
        return jsonify({
            "error": "No URL provided",
            "message": "Please provide a Facebook profile URL using ?url=parameter",
            "example": "/api/all?url=https://www.facebook.com/username",
            "developer": "@imrulbhai69",
            "time_taken": f"{time.time() - request_start:.2f}s"
        }), 400

    if 'facebook.com' not in profile_url:
        return jsonify({
            "error": "Invalid URL",
            "message": "Please provide a valid Facebook profile URL",
            "developer": "@imrulbhai69",
            "time_taken": f"{time.time() - request_start:.2f}s"
        }), 400

    logger.info(f"Processing all images request: {profile_url}")

    try:
        scraper = FacebookProfileScraper()
        result = scraper.scrape_profile(profile_url)

        if result:
            response_data = {
                "success": True,
                "profile_picture": {
                    "standard": result['profile_picture'],
                    "hd": result['profile_picture_hd']
                },
                "cover_photo": {
                    "standard": result['cover_photo'],
                    "hd": result['cover_photo_hd']
                },
                "photos": result['photo_images'],
                "all_images": result['all_images'],
                "total_count": len(result['all_images']),
                "developer": "@imrulbhai69",
                "channel": "t.me/TheSmartDev",
                "time_taken": f"{time.time() - request_start:.2f}s",
                "api_uptime": str(datetime.now() - start_time)
            }
            return jsonify(response_data), 200

        return jsonify({
            "error": "Failed to scrape profile",
            "message": "Could not extract data from the provided URL (maybe private/login required or blocked)",
            "developer": "@imrulbhai69",
            "time_taken": f"{time.time() - request_start:.2f}s"
        }), 404

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({
            "error": "Processing failed",
            "message": "Unable to process the request",
            "developer": "@imrulbhai69",
            "time_taken": f"{time.time() - request_start:.2f}s"
        }), 500


if __name__ == '__main__':
    print("Facebook Profile Scraper API v2.3 + Imrul’s Zone UI")
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    import os

if name == "main":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
