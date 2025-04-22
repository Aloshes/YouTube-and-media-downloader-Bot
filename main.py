import os
import logging
import tempfile
import json
import requests
from flask import Flask, request, jsonify
import yt_dlp as youtube_dl
from urllib.parse import quote, unquote

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

app = Flask(__name__)

# Configuration
TOKEN = os.environ['BOT_TOKEN']
API_URL = f"https://api.telegram.org/bot{TOKEN}/"
DONATION_URL = "https://www.buymeacoffee.com/yourusername"

# YouTube DL configuration
YDL_OPTS = {
    'quiet': True,
    'no_check_certificate': True,
    'ignoreerrors': False,
    'force_generic_extractor': True,
    'geo_bypass': True,
    'referer': 'https://www.youtube.com/',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'cookiefile': None,
}

def send_message(chat_id, text, reply_markup=None):
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    if reply_markup:
        data['reply_markup'] = reply_markup
    try:
        requests.post(API_URL + 'sendMessage', json=data)
    except Exception as e:
        logging.error(f"Failed to send message: {str(e)}")

def process_youtube(url, chat_id):
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '🎥 Video', 'callback_data': f'yt_video_{quote(url)}'},
                {'text': '🎵 Audio', 'callback_data': f'yt_audio_{quote(url)}'}
            ]
        ]
    }
    send_message(chat_id, "Choose download type:", json.dumps(keyboard))

def get_video_keyboard(url):
    try:
        ydl = youtube_dl.YoutubeDL(YDL_OPTS)
        info = ydl.extract_info(url, download=False)
        
        if not info:
            logging.error("Failed to get video info")
            return None
            
        formats = info.get('formats', [])
        if not formats:
            logging.error("No formats available")
            return None

        buttons = []
        for f in formats:
            if f.get('vcodec') != 'none':  # Relaxed check for video formats
                quality = f.get('format_note') or f"{f.get('height', '?')}p"
                ext = f.get('ext', 'mp4')
                buttons.append([{
                    'text': f"{quality} ({ext})",
                    'callback_data': f"vid_{f['format_id']}_{quote(url)}"
                }])

        return {'inline_keyboard': buttons[:10]}  # Limit to first 10 formats

    except Exception as e:
        logging.error(f"Error getting video formats: {str(e)}")
        return None

def get_audio_keyboard(url):
    keyboard = {
        'inline_keyboard': [
            [
                {'text': 'MP3', 'callback_data': f'aud_mp3_{quote(url)}'},
                {'text': 'M4A', 'callback_data': f'aud_m4a_{quote(url)}'}
            ]
        ]
    }
    return keyboard

def get_quality_keyboard(url, format_type):
    keyboard = {
        'inline_keyboard': [
            [
                {'text': 'High', 'callback_data': f'{format_type}_high_{quote(url)}'},
                {'text': 'Medium', 'callback_data': f'{format_type}_med_{quote(url)}'},
                {'text': 'Low', 'callback_data': f'{format_type}_low_{quote(url)}'}
            ]
        ]
    }
    return keyboard

def download_media(url, chat_id, ydl_opts=None, is_video=True):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_opts = YDL_OPTS.copy()
            base_opts.update({
                'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
                'progress_hooks': [lambda d: progress_hook(d, chat_id)]
            })
            
            if ydl_opts:
                base_opts.update(ydl_opts)
            
            # Bypass age restriction
            clean_url = url.replace('youtube.com/watch?v=', 'youtube.com/embed/')
            
            with youtube_dl.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                filepath = ydl.prepare_filename(info)
                
                if is_video:
                    with open(filepath, 'rb') as f:
                        requests.post(API_URL + 'sendVideo',
                                    data={'chat_id': chat_id},
                                    files={'video': f})
                else:
                    with open(filepath, 'rb') as f:
                        requests.post(API_URL + 'sendAudio',
                                    data={'chat_id': chat_id},
                                    files={'audio': f})
                
    except youtube_dl.utils.DownloadError as e:
        error_msg = f"❌ Download error: {str(e)}"
        if "Private video" in str(e):
            error_msg = "❌ This video is private"
        elif "Members-only content" in str(e):
            error_msg = "❌ Members-only content"
        send_message(chat_id, error_msg)
        logging.error(f"Download failed: {str(e)}")
    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")
        logging.error(f"Download failed: {str(e)}")

def progress_hook(d, chat_id):
    if d['status'] == 'downloading':
        progress = d.get('_percent_str', '')
        if progress:
            send_message(chat_id, f"⬇️ Downloading... {progress}")

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = request.get_json()
    
    if 'message' in update:
        msg = update['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        
        if text.startswith('/start'):
            send_message(chat_id, 
                "📥 *YouTube & Media Download Bot*\n\n"
                "Send me any YouTube link to download videos or audio!\n"
                "Features:\n"
                "- Multiple quality options\n"
                "- MP3/M4A conversion\n"
                "- No size limits\n\n"
                "Commands:\n"
                "/donate - Support development\n"
                "/help - Show help", None)
        
        elif text.startswith('/donate'):
            keyboard = {
                'inline_keyboard': [[
                    {'text': '☕ Buy Me a Coffee', 'url': DONATION_URL}
                ]]
            }
            send_message(chat_id, "Support this bot's development:", json.dumps(keyboard))
        
        elif text.startswith('/help'):
            send_message(chat_id, 
                "ℹ️ *Help*\n\n"
                "Just send a YouTube URL and choose options!\n"
                "1. Send YouTube link\n"
                "2. Choose Video/Audio\n"
                "3. Select quality/format\n"
                "4. Wait for download!\n\n"
                "Note: Some videos might have restrictions.")
        
        elif 'youtube.com' in text or 'youtu.be' in text:
            process_youtube(text, chat_id)
        
        else:
            try:
                headers = {'User-Agent': YDL_OPTS['user_agent']}
                response = requests.head(text, headers=headers, timeout=10)
                content_type = response.headers.get('Content-Type', '')
                
                if 'video' in content_type:
                    requests.post(API_URL + 'sendVideo', 
                               json={'chat_id': chat_id, 'video': text})
                elif 'audio' in content_type:
                    requests.post(API_URL + 'sendAudio',
                               json={'chat_id': chat_id, 'audio': text})
                else:
                    send_message(chat_id, "❌ Unsupported media type")
            except Exception as e:
                send_message(chat_id, f"❌ Failed to download media: {str(e)}")
    
    elif 'callback_query' in update:
        cq = update['callback_query']
        data = cq['data']
        chat_id = cq['message']['chat']['id']
        message_id = cq['message']['message_id']
        url = unquote(data.split('_')[-1])
        
        try:
            if data.startswith('yt_video_'):
                keyboard = get_video_keyboard(url)
                if keyboard:
                    requests.post(API_URL + 'editMessageText', json={
                        'chat_id': chat_id,
                        'message_id': message_id,
                        'text': 'Available video qualities:',
                        'reply_markup': json.dumps(keyboard)
                    })
                else:
                    send_message(chat_id, "❌ Failed to get video formats")
            
            elif data.startswith('yt_audio_'):
                keyboard = get_audio_keyboard(url)
                requests.post(API_URL + 'editMessageText', json={
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'text': 'Select audio format:',
                    'reply_markup': json.dumps(keyboard)
                })
            
            elif data.startswith('aud_'):
                parts = data.split('_')
                format_type = parts[1]
                keyboard = get_quality_keyboard(url, format_type)
                requests.post(API_URL + 'editMessageText', json={
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'text': 'Select audio quality:',
                    'reply_markup': json.dumps(keyboard)
                })
            
            elif data.startswith(('mp3_', 'm4a_')):
                parts = data.split('_')
                format_type = parts[0]
                quality = parts[1]
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': format_type,
                        'preferredquality': '320' if quality == 'high' else '192' if quality == 'med' else '128'
                    }]
                }
                download_media(url, chat_id, ydl_opts=ydl_opts, is_video=False)
            
            elif data.startswith('vid_'):
                format_id = data.split('_')[1]
                ydl_opts = {'format': format_id}
                download_media(url, chat_id, ydl_opts=ydl_opts, is_video=True)
            
            requests.post(API_URL + 'answerCallbackQuery', 
                        json={'callback_query_id': cq['id']})
        
        except Exception as e:
            send_message(chat_id, f"❌ Error processing request: {str(e)}")
            logging.error(f"Callback error: {str(e)}")
    
    return jsonify({'status': 'ok'})

@app.route('/')
def home():
    return 'YouTube Download Bot is Running!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
