#!/usr/bin/env python3
"""
Mighty Raffle Bot - Improved Server (Based on Go Implementation)
Key: Solves fresh Turnstile token for EACH draw attempt
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import time
import random
import json
import os
from concurrent.futures import ThreadPoolExecutor
import threading
from urllib.parse import urlparse

try:
    from curl_cffi import requests as curl_requests
    USE_CURL_CFFI = True
    print("[INIT] Using curl_cffi")
except ImportError:
    import requests
    USE_CURL_CFFI = False
    print("[INIT] Using requests")

app = Flask(__name__)
CORS(app)

executor = ThreadPoolExecutor(max_workers=10)
session_lock = threading.Lock()
sessions = []

# Configuration
CAPSOLVER_API_KEY = os.environ.get('CAPSOLVER_API_KEY', "CAP-5B4A34CAC19590EA37662D97C6622A7E219BCD475F8EDB2D082940AFF34733CE")
TURNSTILE_SITE_KEY = "0x4AAAAAAAOvhBMVIyoS3i1k"
TURNSTILE_PAGE_URL = "https://mighty.ph/login"

# Proxy configuration
PROXY_URL = os.environ.get('PROXY_URL', None)

def parse_proxy():
    """Parse proxy URL"""
    if not PROXY_URL:
        return None
    
    try:
        parsed = urlparse(PROXY_URL)
        if parsed.scheme and parsed.netloc:
            proxy_dict = {
                'http': PROXY_URL,
                'https': PROXY_URL
            }
            print(f"[PROXY] Configured: {parsed.netloc.split('@')[-1]}")
            return proxy_dict
    except Exception as e:
        print(f"[PROXY] Error: {e}")
    
    return None

PROXIES = parse_proxy()

def get_realistic_headers():
    """Generate realistic headers like the Go version"""
    return {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://mighty.ph',
        'Referer': 'https://mighty.ph/',
        'Sec-Ch-Ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }

def get_session():
    """Get or create a session"""
    with session_lock:
        if not sessions:
            if USE_CURL_CFFI:
                session = curl_requests.Session(
                    proxies=PROXIES if PROXIES else None
                )
                return session
            else:
                session = requests.Session()
                if PROXIES:
                    session.proxies.update(PROXIES)
                return session
        return sessions.pop()

def return_session(session):
    """Return session to pool"""
    with session_lock:
        if len(sessions) < 10:
            sessions.append(session)

accounts = []
accounts_lock = threading.Lock()

@app.route('/')
def index():
    possible_paths = [
        'mighty_web_app.html',
        './mighty_web_app.html',
        os.path.join(os.path.dirname(__file__), 'mighty_web_app.html'),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return send_file(path)
    
    return jsonify({
        'status': 'online',
        'name': 'Mighty Raffle Bot API (Go-Style)',
        'version': '5.0',
        'note': 'Fresh Turnstile token per draw (like Go version)',
        'proxy': 'enabled' if PROXIES else 'disabled',
    }), 200

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'healthy',
        'proxy': 'enabled' if PROXIES else 'disabled',
        'timestamp': time.time()
    })

@app.route('/api/turnstile', methods=['POST'])
def solve_turnstile():
    """
    Solve Turnstile captcha
    IMPORTANT: Based on Go code, this should be called for EVERY draw, not just login
    """
    if not CAPSOLVER_API_KEY:
        return jsonify({'success': False, 'error': 'API key not configured'}), 400
    
    try:
        session = get_session()
        
        print(f"[TURNSTILE] Creating task...")
        
        # Step 1: Create task
        create_payload = {
            'clientKey': CAPSOLVER_API_KEY,
            'task': {
                'type': 'AntiTurnstileTaskProxyLess',
                'websiteURL': TURNSTILE_PAGE_URL,
                'websiteKey': TURNSTILE_SITE_KEY
            }
        }
        
        if USE_CURL_CFFI:
            response = session.post('https://api.capsolver.com/createTask',
                json=create_payload,
                impersonate="chrome120",
                timeout=30
            )
        else:
            response = session.post('https://api.capsolver.com/createTask',
                json=create_payload,
                timeout=30
            )
        
        result = response.json()
        
        if result.get('errorId', 0) != 0:
            error = result.get('errorDescription', 'Unknown error')
            print(f"[TURNSTILE] ✗ Error: {error}")
            return jsonify({'success': False, 'error': error}), 400
        
        task_id = result.get('taskId')
        print(f"[TURNSTILE] Task created: {task_id}")
        
        # Step 2: Poll for result (like Go version - max 40 attempts, 3 sec each = 2 min timeout)
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
                print(f"[TURNSTILE] ✓ Solved (attempt {i+1})")
                return jsonify({'success': True, 'token': token})
            elif result_data.get('status') == 'failed':
                print(f"[TURNSTILE] ✗ Task failed")
                return jsonify({'success': False, 'error': 'Task failed'}), 400
        
        print(f"[TURNSTILE] ✗ Timeout after 2 minutes")
        return jsonify({'success': False, 'error': 'Timeout'}), 408
        
    except Exception as e:
        print(f"[TURNSTILE] ✗ Exception: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        return_session(session)

@app.route('/api/login', methods=['POST'])
def login():
    """
    Login endpoint - matches Go implementation
    Uses cfts_v3 for login (not cfts_v2)
    """
    data = request.json
    username = data.get('username')
    password = data.get('password')
    turnstile_token = data.get('turnstileToken')
    
    if not turnstile_token:
        return jsonify({'success': False, 'message': 'Turnstile token required'}), 400
    
    print(f"[LOGIN] Attempting: {username}")
    
    session = get_session()
    try:
        headers = get_realistic_headers()
        
        # Go code uses cfts_v3 for login
        payload = {
            'username': username,
            'password': password,
            'cfts_v3': turnstile_token  # Important: v3 for login!
        }
        
        # Add delay like Go version (5 seconds between accounts)
        time.sleep(random.uniform(1.0, 2.0))
        
        if USE_CURL_CFFI:
            response = session.post(
                'https://be.mighty.ph/api/v1/login',
                headers=headers,
                json=payload,
                impersonate="chrome120",
                timeout=30
            )
        else:
            response = session.post(
                'https://be.mighty.ph/api/v1/login',
                headers=headers,
                json=payload,
                timeout=30
            )
        
        status = response.status_code
        print(f"[LOGIN] Status: {status}")
        
        if status == 403:
            print(f"[LOGIN] ✗ 403 Cloudflare block")
            msg = "Cloudflare blocked. "
            if not PROXIES:
                msg += "Solution: Deploy to Fly.io Singapore or use residential proxy"
            else:
                msg += "Proxy detected. Try: 1) Residential proxy 2) Fly.io Singapore"
            return jsonify({'success': False, 'message': msg}), 403
        
        if status == 503:
            return jsonify({'success': False, 'message': 'Service unavailable'}), 503
        
        if status == 429:
            return jsonify({'success': False, 'message': 'Rate limited'}), 429
        
        text = response.text
        
        # Check for HTML (Cloudflare challenge)
        if text.strip().startswith('<') or '<html' in text.lower():
            print(f"[LOGIN] ✗ Cloudflare HTML response")
            return jsonify({
                'success': False,
                'message': 'Cloudflare challenge. Deploy to Fly.io Singapore for best results'
            }), 403
        
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            print(f"[LOGIN] ✗ Invalid JSON")
            return jsonify({'success': False, 'message': 'Invalid response'}), 500
        
        # Check success (code 200 like Go version)
        if result.get('code') == 200:
            if result.get('data') and result['data'].get('token'):
                print(f"[LOGIN] ✓ {username} SUCCESS!")
                return jsonify({
                    'success': True,
                    'token': result['data']['token'],
                    'user': result['data'].get('user', {})
                })
        
        error_msg = result.get('message', 'Unknown error')
        print(f"[LOGIN] ✗ {username}: {error_msg}")
        
        if 'not found' in error_msg.lower():
            error_msg = "Account not found"
        elif 'invalid' in error_msg.lower():
            error_msg = "Invalid credentials"
        
        return jsonify({'success': False, 'message': error_msg}), 401
            
    except Exception as e:
        print(f"[LOGIN] ✗ Exception: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        return_session(session)

@app.route('/api/raffles', methods=['GET'])
def get_raffles():
    """Get available raffles - same as Go version"""
    session = get_session()
    try:
        headers = get_realistic_headers()
        del headers['Content-Type']
        
        if USE_CURL_CFFI:
            response = session.get('https://be.mighty.ph/api/v1/raffles',
                headers=headers,
                impersonate="chrome120",
                timeout=30
            )
        else:
            response = session.get('https://be.mighty.ph/api/v1/raffles',
                headers=headers,
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
    """
    Execute raffle draw - matches Go implementation
    IMPORTANT: Uses cfts_v2 for draws (not cfts_v3)!
    """
    data = request.json
    token = data.get('token')
    raffle_id = data.get('raffleId')
    turnstile_token = data.get('turnstileToken')
    
    # Generate browser ID like Go version
    timestamp = int(time.time() * 1000000000)
    random_part = random.randint(0, 1000000000000)
    browser_id = f"{timestamp:x}{random_part:x}"
    
    session = get_session()
    try:
        headers = get_realistic_headers()
        headers['Authorization'] = f'Bearer {token}'
        headers['Host'] = 'be.mighty.ph'
        
        # IMPORTANT: Go code uses cfts_v2 for draws, not cfts_v3!
        payload = {
            'browser_id': browser_id,
            'cfts_v2': turnstile_token  # v2 for draws!
        }
        
        # Add jitter like Go version
        jitter = random.uniform(0, 2.0)
        time.sleep(jitter)
        
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
        
        # Check for rate limit (status 429)
        if response.status_code == 429:
            return jsonify({'success': False, 'isRateLimit': True, 'message': 'Rate limited'})
        
        text = response.text
        
        # Check for rate limit text
        if text.startswith('Too many'):
            return jsonify({'success': False, 'isRateLimit': True, 'message': text})
        
        # Check for Cloudflare HTML
        if text.startswith('<'):
            return jsonify({'success': False, 'isRateLimit': False, 'message': 'Cloudflare protection'})
        
        result = response.json()
        
        # Success case (code 201 like Go version)
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
    """Check account points - same as Go version"""
    data = request.json
    token = data.get('token')
    
    session = get_session()
    try:
        headers = get_realistic_headers()
        headers['Authorization'] = f'Bearer {token}'
        del headers['Content-Type']
        
        if USE_CURL_CFFI:
            response = session.get('https://be.mighty.ph/api/v1/user/points',
                headers=headers,
                impersonate="chrome120",
                timeout=30
            )
        else:
            response = session.get('https://be.mighty.ph/api/v1/user/points',
                headers=headers,
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
        'bypass_method': 'curl_cffi' if USE_CURL_CFFI else 'requests',
        'proxy': 'enabled' if PROXIES else 'disabled',
        'implementation': 'Go-style (fresh token per draw)',
        'timestamp': time.time()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))
    
    print(f"""
╔═══════════════════════════════════════════════════════╗
║   Mighty Raffle Bot - Go-Style Server v5.0           ║
╠═══════════════════════════════════════════════════════╣
║                                                       ║
║  Implementation: Based on Go code                     ║
║  Key Feature:    Fresh Turnstile per draw            ║
║  Bypass:         {('curl_cffi' if USE_CURL_CFFI else 'requests'):<36} ║
║  Proxy:          {('ENABLED' if PROXIES else 'DISABLED'):<36} ║
║                                                       ║
║  IMPORTANT NOTES:                                     ║
║  • Login uses cfts_v3                                 ║
║  • Draws use cfts_v2                                  ║
║  • Fresh token solved for EACH draw                   ║
║  • 6-8 second delays between attempts                 ║
║                                                       ║
{"║  ⚠️  No proxy - High Cloudflare block rate         ║" if not PROXIES else "║  ✓ Proxy configured                                ║"}
{"║     Best solution: Fly.io Singapore                ║" if not PROXIES else ""}
║                                                       ║
╚═══════════════════════════════════════════════════════╝
    """)
    
    try:
        from waitress import serve
        print("[*] Starting with Waitress...")
        serve(app, host='0.0.0.0', port=port, threads=10)
    except ImportError:
        print("[!] Using Flask server")
        app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
