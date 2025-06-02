#!/usr/bin/env python3

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from urllib.parse import urlparse
import os

app = Flask(__name__)
app.config['DATABASE'] = 'tumblr_backup.db'
app.config['MEDIA_FOLDER'] = 'media'

def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def format_post_content(post):
    """Format post content based on type"""
    raw_data = json.loads(post['raw_data']) if post['raw_data'] else {}

    content = {
        'title': '',
        'body': '',
        'summary': post['summary'] or '',
        'photos': [],
        'video_url': '',
        'audio_url': '',
        'text': '',
        'quote': '',
        'source': '',
        'chat': [],
        'link_url': '',
        'description': ''
    }

    post_type = post['type']

    if post_type == 'text':
        content['title'] = raw_data.get('title', '')
        content['body'] = raw_data.get('body', '')

    elif post_type == 'photo':
        content['photos'] = raw_data.get('photos', [])
        content['body'] = raw_data.get('caption', '')

    elif post_type == 'quote':
        content['quote'] = raw_data.get('text', '')
        content['source'] = raw_data.get('source', '')

    elif post_type == 'link':
        content['title'] = raw_data.get('title', '')
        content['link_url'] = raw_data.get('url', '')
        content['description'] = raw_data.get('description', '')

    elif post_type == 'chat':
        content['title'] = raw_data.get('title', '')
        content['chat'] = raw_data.get('dialogue', [])

    elif post_type == 'video':
        content['video_url'] = raw_data.get('video_url', '')
        content['body'] = raw_data.get('caption', '')

    elif post_type == 'audio':
        content['audio_url'] = raw_data.get('audio_url', '')
        content['body'] = raw_data.get('caption', '')

    return content

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '')
    post_type = request.args.get('type', '')
    blog = request.args.get('blog', 'febuiles')

    conn = get_db_connection()
    where_conditions = []
    params = []

    if search:
        where_conditions.append("(posts.summary LIKE ? OR posts.raw_data LIKE ?)")
        params.extend([f'%{search}%', f'%{search}%'])

    if post_type:
        where_conditions.append("posts.type = ?")
        params.append(post_type)

    if blog:
        where_conditions.append("posts.blog_name = ?")
        params.append(blog)

    where_clause = ' AND '.join(where_conditions) if where_conditions else '1=1'
    count_query = f"SELECT COUNT(*) FROM posts WHERE {where_clause}"
    total_posts = conn.execute(count_query, params).fetchone()[0]
    offset = (page - 1) * per_page
    query = f"""
        SELECT * FROM posts
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """
    posts = conn.execute(query, params + [per_page, offset]).fetchall()
    blogs = conn.execute("SELECT DISTINCT blog_name FROM posts ORDER BY blog_name").fetchall()
    types = conn.execute("SELECT DISTINCT type FROM posts ORDER BY type").fetchall()

    conn.close()
    total_pages = (total_posts + per_page - 1) // per_page

    return render_template('index.html',
                         posts=posts,
                         page=page,
                         total_pages=total_pages,
                         total_posts=total_posts,
                         search=search,
                         post_type=post_type,
                         blog=blog,
                         blogs=blogs,
                         types=types,
                         format_post_content=format_post_content)

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    conn = get_db_connection()

    post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        return "Post not found", 404
    media = conn.execute("""
        SELECT * FROM media
        WHERE post_id = ? AND downloaded = 1
        ORDER BY id
    """, (post_id,)).fetchall()
    tags = conn.execute("""
        SELECT tags.tag_name
        FROM tags
        JOIN post_tags ON tags.id = post_tags.tag_id
        WHERE post_tags.post_id = ?
        ORDER BY tags.tag_name
    """, (post_id,)).fetchall()

    conn.close()

    return render_template('post_detail.html',
                         post=post,
                         media=media,
                         tags=tags,
                         format_post_content=format_post_content)

@app.route('/media/<path:filename>')
def serve_media(filename):
    return send_from_directory(app.config['MEDIA_FOLDER'], filename)

@app.route('/stats')
def stats():
    conn = get_db_connection()

    stats_data = {}
    type_counts = conn.execute("""
        SELECT type, COUNT(*) as count
        FROM posts
        GROUP BY type
        ORDER BY count DESC
    """).fetchall()
    blog_counts = conn.execute("""
        SELECT blog_name, COUNT(*) as count
        FROM posts
        GROUP BY blog_name
        ORDER BY count DESC
    """).fetchall()
    media_stats = conn.execute("""
        SELECT
            COUNT(*) as total_media,
            SUM(CASE WHEN downloaded = 1 THEN 1 ELSE 0 END) as downloaded_media,
            COUNT(DISTINCT media_type) as media_types
        FROM media
    """).fetchone()
    total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    date_range = conn.execute("""
        SELECT MIN(date) as earliest, MAX(date) as latest
        FROM posts
    """).fetchone()

    conn.close()

    stats_data = {
        'total_posts': total_posts,
        'type_counts': type_counts,
        'blog_counts': blog_counts,
        'media_stats': media_stats,
        'date_range': date_range
    }

    return render_template('stats.html', stats=stats_data)

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    conn = get_db_connection()
    results = conn.execute("""
        SELECT id, blog_name, type, summary, date
        FROM posts
        WHERE summary LIKE ? OR raw_data LIKE ?
        ORDER BY timestamp DESC
        LIMIT 10
    """, (f'%{query}%', f'%{query}%')).fetchall()
    conn.close()

    return jsonify([dict(row) for row in results])

if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE']):
        print(f"Database {app.config['DATABASE']} not found!")
        print("Please run 'python tumblr_backup.py' first to create the database.")
        exit(1)

    print("Starting Tumblr Backup Viewer...")
    print("Open http://localhost:3000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=3000)
