"""
YouTube Downloader Backend API - FIXED VERSION
Flask + yt-dlp with proper error handling
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import hashlib
import time
from pathlib import Path
import logging
import traceback

app = Flask(__name__)
CORS(app)

# Enhanced logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
                    logger.info(f"Cleaned up: {filename}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def extract_video_id(url):
    import re
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
        r'youtube\.com\/embed\/([^&\n?#]+)',
        r'youtube\.com\/v\/([^&\n?#]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

@app.route('/')
def index():
    return jsonify({
        'name': 'YouTube Downloader API - FIXED',
        'version': '2.0',
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
        
        logger.info(f"Info request for: {url}")
        
        if not url:
            return jsonify({'success': False, 'error': 'URL required'}), 400
        
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            logger.info(f"Info retrieved for: {info.get('title')}")
            
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
        logger.error(f"Info error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Failed to get video info: {str(e)}'
        }), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    try:
        cleanup_old_files()
        
        data = request.json
        url = data.get('url')
        format_type = data.get('format', 'mp4')
        quality = data.get('quality', '720')
        
        logger.info(f"Download request - URL: {url}, Format: {format_type}, Quality: {quality}")
        
        if not url:
            return jsonify({'success': False, 'error': 'URL required'}), 400
        
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400
        
        # Generate unique filename
        timestamp = int(time.time())
        filename_hash = hashlib.md5(f"{video_id}{format_type}{quality}{timestamp}".encode()).hexdigest()[:8]
        
        if format_type == 'mp3':
            # MP3 download options
            output_template = os.path.join(DOWNLOAD_FOLDER, f'{filename_hash}')
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality,
                }],
                'quiet': False,
                'no_warnings': False,
                'verbose': True,
            }
        else:
            # MP4 download options
            output_template = os.path.join(DOWNLOAD_FOLDER, f'{filename_hash}')
            
            # Simplified format selection for Railway
            if quality == '720':
                format_selector = 'best[height<=720][ext=mp4]/best[height<=720]/best'
            elif quality == '480':
                format_selector = 'best[height<=480][ext=mp4]/best[height<=480]/best'
            else:  # 360
                format_selector = 'best[height<=360][ext=mp4]/best[height<=360]/best'
            
            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'quiet': False,
                'no_warnings': False,
                'verbose': True,
            }
        
        logger.info(f"Starting download with options: {ydl_opts}")
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            
            logger.info(f"Download completed: {title}")
            
            # Find the downloaded file
            downloaded_file = None
            possible_extensions = ['mp3', 'mp4', 'm4a', 'webm', 'mkv']
            
            for ext in possible_extensions:
                potential_file = f"{output_template}.{ext}"
                logger.info(f"Checking for file: {potential_file}")
                if os.path.exists(potential_file):
                    downloaded_file = potential_file
                    logger.info(f"Found file: {downloaded_file}")
                    break
            
            # Also check without extension
            if not downloaded_file and os.path.exists(output_template):
                downloaded_file = output_template
                logger.info(f"Found file without extension: {downloaded_file}")
            
            if not downloaded_file:
                # List all files in download folder for debugging
                all_files = os.listdir(DOWNLOAD_FOLDER)
                logger.error(f"File not found! Files in directory: {all_files}")
                return jsonify({
                    'success': False,
                    'error': 'Download completed but file not found',
                    'debug': {
                        'expected': output_template,
                        'files': all_files
                    }
                }), 500
            
            # Clean filename for download
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title[:50]  # Limit length
            download_name = f"{safe_title}.{format_type}"
            
            logger.info(f"Sending file: {downloaded_file} as {download_name}")
            
            # Send file
            response = send_file(
                downloaded_file,
                as_attachment=True,
                download_name=download_name,
                mimetype='audio/mpeg' if format_type == 'mp3' else 'video/mp4'
            )
            
            # Schedule file deletion after sending
            @response.call_on_close
            def cleanup():
                try:
                    if os.path.exists(downloaded_file):
                        os.remove(downloaded_file)
                        logger.info(f"Cleaned up: {downloaded_file}")
                except Exception as e:
                    logger.error(f"Cleanup failed: {e}")
            
            return response
            
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Download failed: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'download_folder': DOWNLOAD_FOLDER,
        'files_count': len(os.listdir(DOWNLOAD_FOLDER))
    })

@app.route('/test')
def test():
    """Test endpoint to verify yt-dlp is working"""
    try:
        ydl_opts = {'quiet': True}
        test_url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(test_url, download=False)
            return jsonify({
                'status': 'yt-dlp working',
                'test_video': info.get('title'),
                'version': yt_dlp.version.__version__
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    logger.info(f"Download folder: {DOWNLOAD_FOLDER}")
    app.run(host='0.0.0.0', port=port, debug=False)
