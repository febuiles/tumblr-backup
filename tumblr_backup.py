#!/usr/bin/env python3

import os
import sqlite3
import logging
import json
import requests
import mimetypes
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import hashlib
import time
from datetime import datetime
from dotenv import load_dotenv
import pytumblr

load_dotenv()

class TumblrBackup:
    def __init__(self):
        self.consumer_key = os.getenv('TUMBLR_CONSUMER_KEY')
        self.consumer_secret = os.getenv('TUMBLR_CONSUMER_SECRET')
        self.access_token = None
        self.access_token_secret = None
        self.client = None
        self.db_path = 'tumblr_backup.db'
        self.media_dir = Path('media')
        self.setup_logging()
        self.setup_directories()
        self.setup_database()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('backup.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def setup_directories(self):
        self.media_dir.mkdir(exist_ok=True)

    def setup_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY,
                blog_name TEXT,
                type TEXT,
                state TEXT,
                format TEXT,
                timestamp INTEGER,
                date TEXT,
                tags TEXT,
                short_url TEXT,
                summary TEXT,
                reblog_key TEXT,
                post_url TEXT,
                slug TEXT,
                note_count INTEGER,
                raw_data TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER,
                media_url TEXT,
                local_path TEXT,
                media_type TEXT,
                width INTEGER,
                height INTEGER,
                original_size INTEGER,
                downloaded BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_name TEXT UNIQUE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_tags (
                post_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY (post_id, tag_id),
                FOREIGN KEY (post_id) REFERENCES posts (id),
                FOREIGN KEY (tag_id) REFERENCES tags (id)
            )
        ''')

        conn.commit()
        conn.close()

    def load_tokens(self):
        token_file = '.tumblr_tokens'
        if os.path.exists(token_file):
            with open(token_file, 'r') as f:
                tokens = json.load(f)
                self.access_token = tokens.get('access_token')
                self.access_token_secret = tokens.get('access_token_secret')
                return True
        return False

    def save_tokens(self, access_token, access_token_secret):
        tokens = {
            'access_token': access_token,
            'access_token_secret': access_token_secret
        }
        with open('.tumblr_tokens', 'w') as f:
            json.dump(tokens, f)
        self.access_token = access_token
        self.access_token_secret = access_token_secret

    def authenticate(self):
        if not self.consumer_key or not self.consumer_secret:
            raise ValueError("TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET must be set in .env file")

        if self.load_tokens():
            self.client = pytumblr.TumblrRestClient(
                self.consumer_key,
                self.consumer_secret,
                self.access_token,
                self.access_token_secret
            )
            try:
                user_info = self.client.info()
                if 'user' in user_info:
                    self.logger.info("Successfully authenticated with existing tokens")
                    return True
            except:
                self.logger.info("Existing tokens invalid, need to re-authenticate")

        print("OAuth tokens not found or invalid.")
        print("Please run the OAuth setup first:")
        print()
        print("  python get_oauth_tokens.py")
        print()
        print("This will guide you through getting your OAuth tokens.")
        print("Alternatively, you can enter them manually now:")
        print()

        self.access_token = input("Enter your OAuth token (or press Enter to run OAuth setup): ").strip()

        if not self.access_token:
            print("Running OAuth setup...")
            try:
                import subprocess
                result = subprocess.run(['python', 'get_oauth_tokens.py'], cwd='.')
                if result.returncode == 0:
                    print("OAuth setup completed. Please run the backup script again.")
                    return False
                else:
                    print("OAuth setup failed. Please run 'python get_oauth_tokens.py' manually.")
                    return False
            except Exception as e:
                print(f"Failed to run OAuth setup: {e}")
                print("Please run 'python get_oauth_tokens.py' manually.")
                return False

        self.access_token_secret = input("Enter your OAuth token secret: ").strip()

        if not self.access_token or not self.access_token_secret:
            print("Invalid tokens provided")
            return False

        self.save_tokens(self.access_token, self.access_token_secret)

        self.client = pytumblr.TumblrRestClient(
            self.consumer_key,
            self.consumer_secret,
            self.access_token,
            self.access_token_secret
        )

        try:
            user_info = self.client.info()
            if 'user' in user_info:
                self.logger.info("Authentication successful!")
                return True
            else:
                self.logger.error("Authentication failed - invalid tokens")
                return False
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False

    def get_user_blogs(self):
        user_info = self.client.info()
        return [blog['name'] for blog in user_info['user']['blogs']]

    def extract_media_urls(self, post):
        media_urls = []
        post_type = post.get('type', '')

        if post_type == 'photo':
            for photo in post.get('photos', []):
                original_size = photo.get('original_size', {})
                if original_size.get('url'):
                    media_urls.append({
                        'url': original_size['url'],
                        'type': 'image',
                        'width': original_size.get('width'),
                        'height': original_size.get('height')
                    })

        elif post_type == 'video':
            video_url = post.get('video_url')
            if video_url:
                media_urls.append({
                    'url': video_url,
                    'type': 'video'
                })

        elif post_type == 'audio':
            audio_url = post.get('audio_url')
            if audio_url:
                media_urls.append({
                    'url': audio_url,
                    'type': 'audio'
                })

        return media_urls

    def download_media(self, media_url, post_id, media_type):
        try:
            response = requests.get(media_url, stream=True, timeout=30)
            response.raise_for_status()

            parsed_url = urlparse(media_url)
            filename = os.path.basename(parsed_url.path)
            if not filename:
                ext = mimetypes.guess_extension(response.headers.get('content-type', '')) or ''
                filename = f"{hashlib.md5(media_url.encode()).hexdigest()}{ext}"

            post_media_dir = self.media_dir / str(post_id)
            post_media_dir.mkdir(exist_ok=True)

            local_path = post_media_dir / filename

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return str(local_path)

        except Exception as e:
            self.logger.error(f"Failed to download {media_url}: {e}")
            return None

    def save_post(self, post):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        post_id = post['id']

        cursor.execute('SELECT id FROM posts WHERE id = ?', (post_id,))
        if cursor.fetchone():
            conn.close()
            return False

        cursor.execute('''
            INSERT INTO posts (
                id, blog_name, type, state, format, timestamp, date, tags,
                short_url, summary, reblog_key, post_url, slug, note_count, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            post_id,
            post.get('blog_name'),
            post.get('type'),
            post.get('state'),
            post.get('format'),
            post.get('timestamp'),
            post.get('date'),
            ','.join(post.get('tags', [])),
            post.get('short_url'),
            post.get('summary'),
            post.get('reblog_key'),
            post.get('post_url'),
            post.get('slug'),
            post.get('note_count'),
            json.dumps(post)
        ))

        for tag in post.get('tags', []):
            cursor.execute('INSERT OR IGNORE INTO tags (tag_name) VALUES (?)', (tag,))
            cursor.execute('SELECT id FROM tags WHERE tag_name = ?', (tag,))
            tag_id = cursor.fetchone()[0]
            cursor.execute('INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)', (post_id, tag_id))

        media_urls = self.extract_media_urls(post)
        for media in media_urls:
            cursor.execute('''
                INSERT INTO media (post_id, media_url, media_type, width, height)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                post_id,
                media['url'],
                media['type'],
                media.get('width'),
                media.get('height')
            ))

        conn.commit()
        conn.close()
        return True

    def download_all_media(self, max_workers=5):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT id, post_id, media_url, media_type FROM media WHERE downloaded = FALSE')
        media_items = cursor.fetchall()
        conn.close()

        if not media_items:
            self.logger.info("No media files to download")
            return

        self.logger.info(f"Downloading {len(media_items)} media files...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_media = {
                executor.submit(self.download_media, url, post_id, media_type): (media_id, url)
                for media_id, post_id, url, media_type in media_items
            }

            completed = 0
            for future in as_completed(future_to_media):
                media_id, url = future_to_media[future]
                local_path = future.result()

                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                if local_path:
                    cursor.execute(
                        'UPDATE media SET local_path = ?, downloaded = TRUE WHERE id = ?',
                        (local_path, media_id)
                    )
                else:
                    cursor.execute(
                        'UPDATE media SET downloaded = TRUE WHERE id = ?',
                        (media_id,)
                    )

                conn.commit()
                conn.close()

                completed += 1
                if completed % 10 == 0:
                    self.logger.info(f"Downloaded {completed}/{len(media_items)} files")

        self.logger.info(f"Media download complete: {completed}/{len(media_items)} files")

    def backup_blog(self, blog_name):
        self.logger.info(f"Starting backup for blog: {blog_name}")

        offset = 0
        limit = 20
        total_posts = 0
        new_posts = 0

        while True:
            posts = self.client.posts(blog_name, limit=limit, offset=offset)

            if 'posts' not in posts or not posts['posts']:
                break

            for post in posts['posts']:
                if self.save_post(post):
                    new_posts += 1
                total_posts += 1

            self.logger.info(f"Processed {total_posts} posts ({new_posts} new)")

            if len(posts['posts']) < limit:
                break

            offset += limit
            time.sleep(0.5)

        self.logger.info(f"Blog backup complete: {total_posts} total posts, {new_posts} new posts")
        return total_posts, new_posts

    def run_backup(self):
        if not self.authenticate():
            return False

        blogs = self.get_user_blogs()
        self.logger.info(f"Found {len(blogs)} blogs: {', '.join(blogs)}")

        total_posts = 0
        total_new = 0

        for blog in blogs:
            posts, new = self.backup_blog(blog)
            total_posts += posts
            total_new += new

        self.logger.info(f"All blogs backed up: {total_posts} total posts, {total_new} new posts")

        self.download_all_media()

        self.logger.info("Backup complete!")
        return True

def main():
    backup = TumblrBackup()
    backup.run_backup()

if __name__ == '__main__':
    main()
