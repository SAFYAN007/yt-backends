"""
YouTube Downloader Backend API
Flask + yt-dlp - Railway/Render Ready
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import hashlib
import time
from pathlib import Path
import logging

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_FOLDER = os.path.join(os.getcwd(), 'downloads')
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
MAX_FILE_AGE = 3600

def cleanup_old_files():
    try:
        current_time = time.time()
        for filename in os.listdir(DOWNLOAD_FOLDER):
            filepath = os.path.join(DOWNLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                if current_time - os.path.getmtime(filepath) > MAX_FILE_AGE:
                    os.remove(filepath)
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def extract_video_id(url):
    import re
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
        r'youtube\.com\/embed\/([^&\n?#]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

@app.route('/')
def index():
    return jsonify({
        'name': 'YouTube Downloader API',
        'version': '1.0',
        'status': 'active',
        'endpoints': {
            '/api/info': 'POST - Get video info',
            '/api/download': 'POST - Download video',
            '/health': 'GET - Health check'
        }
    })

@app.route('/api/info', methods=['POST'])
def get_video_info():
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'success': False, 'error': 'URL required'}), 400
        
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400
        
        ydl_opts = {'quiet': True, 'no_warnings': True}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return jsonify({
                'success': True,
                'data': {
                    'id': video_id,
                    'title': info.get('title'),
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration'),
                    'channel': info.get('uploader')
                }
            })
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    try:
        cleanup_old_files()
        
        data = request.json
        url = data.get('url')
        format_type = data.get('format', 'mp4')
        quality = data.get('quality', '720')
        
        if not url:
            return jsonify({'success': False, 'error': 'URL required'}), 400
        
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400
        
        filename_hash = hashlib.md5(f"{video_id}{format_type}{quality}{time.time()}".encode()).hexdigest()[:8]
        output_template = os.path.join(DOWNLOAD_FOLDER, f'{filename_hash}.%(ext)s')
        
        if format_type == 'mp3':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality,
                }],
                'quiet': True,
            }
        else:
            if quality == '720':
                format_selector = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]'
            elif quality == '480':
                format_selector = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]'
            else:
                format_selector = 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]'
            
            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'quiet': True,
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            
            downloaded_file = None
            for ext in ['mp3', 'mp4', 'm4a', 'webm']:
                potential_file = os.path.join(DOWNLOAD_FOLDER, f'{filename_hash}.{ext}')
                if os.path.exists(potential_file):
                    downloaded_file = potential_file
                    break
            
            if not downloaded_file:
                return jsonify({'success': False, 'error': 'Download failed'}), 500
            
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            download_name = f"{safe_title}.{format_type}"
            
            return send_file(
                downloaded_file,
                as_attachment=True,
                download_name=download_name,
                mimetype='audio/mpeg' if format_type == 'mp3' else 'video/mp4'
            )
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
