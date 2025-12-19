#!/usr/bin/env python3
"""
Mighty Raffle Bot - Enhanced Server with Better Cloudflare Bypass
Uses curl_cffi for better success rate
Run: python mighty_server_enhanced.py
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import time
import random
import json
import os
from concurrent.futures import ThreadPoolExecutor
import threading

# Try to import curl_cffi first, fallback to cloudscraper
try:
    from curl_cffi import requests as curl_requests
    USE_CURL_CFFI = True
    print("[INIT] Using curl_cffi for better Cloudflare bypass")
except ImportError:
    import cloudscraper
    USE_CURL_CFFI = False
    print("[INIT] Using cloudscraper (install curl_cffi for better results)")

app = Flask(__name__)
CORS(app)

# Thread pool for handling concurrent requests
executor = ThreadPoolExecutor(max_workers=10)

# Thread-safe session pool
session_lock = threading.Lock()
sessions = []

def get_session():
    """Get or create a session"""
    with session_lock:
        if not sessions:
            if USE_CURL_CFFI:
                # curl_cffi with browser impersonation
                session = curl_requests.Session()
                return session
            else:
                # cloudscraper fallback
                return cloudscraper.create_scraper(
                    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
                )
        return sessions.pop()

def return_session(session):
    """Return session to pool"""
    with session_lock:
        if len(sessions) < 10:
            sessions.append(session)

# Configuration
CAPSOLVER_API_KEY = os.environ.get('CAPSOLVER_API_KEY', "CAP-5B4A34CAC19590EA37662D97C6622A7E219BCD475F8EDB2D082940AFF34733CE")
TURNSTILE_SITE_KEY = "0x4AAAAAAAOvhBMVIyoS3i1k"
TURNSTILE_PAGE_URL = "https://mighty.ph/login"

accounts = []
accounts_lock = threading.Lock()

@app.route('/')
def index():
    """Serve the main HTML file or API info"""
    possible_paths = [
        'mighty_web_app.html',
        './mighty_web_app.html',
        os.path.join(os.path.dirname(__file__), 'mighty_web_app.html'),
        '/app/mighty_web_app.html',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return send_file(path)
    
    return jsonify({
        'status': 'online',
        'name': 'Mighty Raffle Bot API',
        'version': '2.0 - Enhanced',
        'cloudflare_bypass': 'curl_cffi' if USE_CURL_CFFI else 'cloudscraper',
        'endpoints': {
            'GET /': 'API info or HTML',
            'GET /api/health': 'Health check',
            'POST /api/turnstile': 'Solve Turnstile',
            'POST /api/login': 'Login account',
            'GET /api/raffles': 'Get raffles',
            'POST /api/draw': 'Execute draw',
            'POST /api/check-points': 'Check points'
        }
    }), 200

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

@app.route('/api/turnstile', methods=['POST'])
def solve_turnstile():
    """Solve Turnstile captcha"""
    if not CAPSOLVER_API_KEY:
        return jsonify({'success': False, 'error': 'API key not configured'}), 400
    
    try:
        session = get_session()
        
        # Create task
        if USE_CURL_CFFI:
            response = session.post('https://api.capsolver.com/createTask',
                json={
                    'clientKey': CAPSOLVER_API_KEY,
                    'task': {
                        'type': 'AntiTurnstileTaskProxyLess',
                        'websiteURL': TURNSTILE_PAGE_URL,
                        'websiteKey': TURNSTILE_SITE_KEY
                    }
                },
                impersonate="chrome120",
                timeout=30
            )
        else:
            response = session.post('https://api.capsolver.com/createTask',
                json={
                    'clientKey': CAPSOLVER_API_KEY,
                    'task': {
                        'type': 'AntiTurnstileTaskProxyLess',
                        'websiteURL': TURNSTILE_PAGE_URL,
                        'websiteKey': TURNSTILE_SITE_KEY
                    }
                },
                timeout=30
            )
        
        result = response.json()
        
        if result.get('errorId', 0) != 0:
            return jsonify({'success': False, 'error': result.get('errorDescription', 'Unknown error')}), 400
        
        task_id = result.get('taskId')
        print(f"[TURNSTILE] Task: {task_id}")
        
        # Poll for result
        for i in range(40):
            time.sleep(3)
            
            if USE_CURL_CFFI:
                result_response = session.post('https://api.capsolver.com/getTaskResult',
                    json={'clientKey': CAPSOLVER_API_KEY, 'taskId': task_id},
                    impersonate="chrome120",
                    timeout=30
                )
            else:
                result_response = session.post('https://api.capsolver.com/getTaskResult',
                    json={'clientKey': CAPSOLVER_API_KEY, 'taskId': task_id},
                    timeout=30
                )
            
            result_data = result_response.json()
            
            if result_data.get('status') == 'ready':
                token = result_data['solution']['token']
                print(f"[TURNSTILE] ✓ Solved")
                return jsonify({'success': True, 'token': token})
            elif result_data.get('status') == 'failed':
                return jsonify({'success': False, 'error': 'Task failed'}), 400
        
        return jsonify({'success': False, 'error': 'Timeout'}), 408
        
    except Exception as e:
        print(f"[TURNSTILE] Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        return_session(session)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    turnstile_token = data.get('turnstileToken')
    
    if not turnstile_token:
        return jsonify({'success': False, 'message': 'Turnstile token required'}), 400
    
    print(f"[LOGIN] Attempting login for: {username}")
    
    session = get_session()
    try:
        # Enhanced headers for better success
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://mighty.ph',
            'Referer': 'https://mighty.ph/login',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        payload = {
            'username': username,
            'password': password,
            'cfts_v3': turnstile_token
        }
        
        # Add human-like delay
        time.sleep(random.uniform(1.0, 2.5))
        
        if USE_CURL_CFFI:
            # Use curl_cffi with browser impersonation
            response = session.post(
                'https://be.mighty.ph/api/v1/login',
                headers=headers,
                json=payload,
                impersonate="chrome120",  # Impersonate real Chrome browser
                timeout=30
            )
        else:
            # Use cloudscraper
            response = session.post(
                'https://be.mighty.ph/api/v1/login',
                headers=headers,
                json=payload,
                timeout=30
            )
        
        print(f"[LOGIN] Response status: {response.status_code}")
        
        # Handle various status codes
        if response.status_code == 403:
            print(f"[LOGIN] ✗ Cloudflare 403")
            return jsonify({'success': False, 'message': 'Blocked by Cloudflare - Try VPN or wait 60 seconds'}), 403
        
        if response.status_code == 503:
            print(f"[LOGIN] ✗ Service unavailable")
            return jsonify({'success': False, 'message': 'Service temporarily unavailable'}), 503
        
        if response.status_code == 429:
            print(f"[LOGIN] ✗ Rate limited")
            return jsonify({'success': False, 'message': 'Rate limited - Wait 30 seconds'}), 429
        
        text = response.text
        
        # Check if response is HTML (Cloudflare challenge)
        if text.strip().startswith('<') or '<!DOCTYPE' in text or '<html' in text.lower():
            print(f"[LOGIN] ✗ Received HTML - Cloudflare protection")
            return jsonify({'success': False, 'message': 'Cloudflare challenge detected - Try: 1) Use VPN 2) Wait 60s 3) Deploy to Railway/Render'}), 403
        
        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[LOGIN] ✗ JSON decode error")
            return jsonify({'success': False, 'message': 'Invalid response format'}), 500
        
        # Success case
        if result.get('code') == 200:
            if result.get('data') and result['data'].get('token'):
                print(f"[LOGIN] ✓ {username} - Success!")
                return jsonify({
                    'success': True,
                    'token': result['data']['token'],
                    'user': result['data'].get('user', {})
                })
        
        # Handle errors
        error_msg = result.get('message', 'Unknown error')
        print(f"[LOGIN] ✗ {username}: {error_msg}")
        
        if 'not found' in error_msg.lower():
            error_msg = "Account not found"
        elif 'invalid' in error_msg.lower() or 'incorrect' in error_msg.lower():
            error_msg = "Invalid username or password"
        elif 'turnstile' in error_msg.lower():
            error_msg = "Captcha verification failed"
        
        return jsonify({'success': False, 'message': error_msg}), 401
            
    except Exception as e:
        print(f"[LOGIN] ✗ Exception: {type(e).__name__}: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    finally:
        return_session(session)

@app.route('/api/raffles', methods=['GET'])
def get_raffles():
    """Get available raffles"""
    session = get_session()
    try:
        if USE_CURL_CFFI:
            response = session.get('https://be.mighty.ph/api/v1/raffles',
                headers={
                    'Accept': 'application/json',
                    'Origin': 'https://mighty.ph',
                    'Referer': 'https://mighty.ph/'
                },
                impersonate="chrome120",
                timeout=30
            )
        else:
            response = session.get('https://be.mighty.ph/api/v1/raffles',
                headers={
                    'Accept': 'application/json',
                    'Origin': 'https://mighty.ph',
                    'Referer': 'https://mighty.ph/'
                },
                timeout=30
            )
        
        result = response.json()
        
        if result.get('code') == 200:
            return jsonify({'success': True, 'raffles': result.get('data', [])})
        else:
            return jsonify({'success': False, 'message': result.get('message')}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        return_session(session)

@app.route('/api/draw', methods=['POST'])
def execute_draw():
    data = request.json
    token = data.get('token')
    raffle_id = data.get('raffleId')
    turnstile_token = data.get('turnstileToken')
    
    timestamp = int(time.time() * 1000000000)
    random_part = random.randint(0, 1000000000000)
    browser_id = f"{timestamp:x}{random_part:x}"
    
    session = get_session()
    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}',
            'Origin': 'https://mighty.ph',
            'Referer': 'https://mighty.ph/'
        }
        
        payload = {
            'browser_id': browser_id,
            'cfts_v2': turnstile_token
        }
        
        if USE_CURL_CFFI:
            response = session.put(f'https://be.mighty.ph/api/v1/raffle/register/{raffle_id}',
                headers=headers,
                json=payload,
                impersonate="chrome120",
                timeout=30
            )
        else:
            response = session.put(f'https://be.mighty.ph/api/v1/raffle/register/{raffle_id}',
                headers=headers,
                json=payload,
                timeout=30
            )
        
        if response.status_code == 429:
            return jsonify({'success': False, 'isRateLimit': True, 'message': 'Rate limited'})
        
        text = response.text
        
        if text.startswith('Too many'):
            return jsonify({'success': False, 'isRateLimit': True, 'message': text})
        
        if text.startswith('<'):
            return jsonify({'success': False, 'isRateLimit': False, 'message': 'Cloudflare'})
        
        result = response.json()
        
        if result.get('code') == 201:
            msg = result.get('reward', {}).get('message', 'Success')
            return jsonify({'success': True, 'isRateLimit': False, 'message': msg})
        else:
            msg = result.get('message', 'Unknown error')
            return jsonify({'success': False, 'isRateLimit': False, 'message': msg})
            
    except Exception as e:
        return jsonify({'success': False, 'isRateLimit': False, 'message': str(e)}), 500
    finally:
        return_session(session)

@app.route('/api/check-points', methods=['POST'])
def get_points():
    """Check account points"""
    data = request.json
    token = data.get('token')
    
    session = get_session()
    try:
        if USE_CURL_CFFI:
            response = session.get('https://be.mighty.ph/api/v1/user/points',
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {token}',
                    'Origin': 'https://mighty.ph',
                    'Referer': 'https://mighty.ph/'
                },
                impersonate="chrome120",
                timeout=30
            )
        else:
            response = session.get('https://be.mighty.ph/api/v1/user/points',
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {token}',
                    'Origin': 'https://mighty.ph',
                    'Referer': 'https://mighty.ph/'
                },
                timeout=30
            )
        
        result = response.json()
        
        if result.get('code') == 200:
            return jsonify({
                'success': True,
                'points': result.get('points', 0),
                'redXLPoints': result.get('redXLPoints', 0)
            })
        else:
            return jsonify({'success': False, 'message': result.get('message')}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        return_session(session)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get server statistics"""
    with accounts_lock:
        total_accounts = len(accounts)
    
    return jsonify({
        'status': 'online',
        'totalAccounts': total_accounts,
        'activeThreads': threading.active_count(),
        'sessionPoolSize': len(sessions),
        'bypass_method': 'curl_cffi' if USE_CURL_CFFI else 'cloudscraper',
        'timestamp': time.time()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))
    print(f"""
╔═══════════════════════════════════════════════════════╗
║   Mighty Raffle Bot - Enhanced Production Server     ║
╠═══════════════════════════════════════════════════════╣
║                                                       ║
║  ✓ Enhanced Cloudflare bypass                        ║
║  ✓ {'curl_cffi' if USE_CURL_CFFI else 'cloudscraper':<45} ║
║  ✓ Multi-threaded operations                         ║
║  ✓ Session pooling enabled                           ║
║                                                       ║
║  Server: http://0.0.0.0:{port}                       ║
║                                                       ║
║  TIP: Install curl_cffi for better success rate:     ║
║       pip install curl_cffi                          ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
    """)
    
    try:
        from waitress import serve
        print("[*] Starting with Waitress...")
        serve(app, host='0.0.0.0', port=port, threads=10)
    except ImportError:
        print("[!] Using Flask development server")
        app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
