#!/usr/bin/env python3
"""
Mighty Raffle Bot - Production Server (FIXED)
Handles multiple accounts with better performance
Run: python mighty_server.py
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import cloudscraper
import requests
import time
import random
import json
import os
from concurrent.futures import ThreadPoolExecutor
import threading

app = Flask(__name__)
CORS(app)

# Thread pool for handling concurrent requests
executor = ThreadPoolExecutor(max_workers=10)

# Thread-safe session pool
session_lock = threading.Lock()
scrapers = []

def get_scraper():
    """Get or create a cloudscraper session"""
    with session_lock:
        if not scrapers:
            return cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
            )
        return scrapers.pop()

def return_scraper(scraper):
    """Return scraper to pool"""
    with session_lock:
        if len(scrapers) < 10:  # Keep max 10 scrapers in pool
            scrapers.append(scraper)

# Configuration - Get from environment or use default
CAPSOLVER_API_KEY = os.environ.get('CAPSOLVER_API_KEY', "CAP-5B4A34CAC19590EA37662D97C6622A7E219BCD475F8EDB2D082940AFF34733CE")
TURNSTILE_SITE_KEY = "0x4AAAAAAAOvhBMVIyoS3i1k"
TURNSTILE_PAGE_URL = "https://mighty.ph/login"

accounts = []
accounts_lock = threading.Lock()

@app.route('/')
def index():
    """Serve the main HTML file or API info"""
    # Try to find and serve the HTML file
    possible_paths = [
        'mighty_web_app.html',
        './mighty_web_app.html',
        os.path.join(os.path.dirname(__file__), 'mighty_web_app.html'),
        '/app/mighty_web_app.html',  # For some hosting platforms
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return send_file(path)
    
    # If HTML not found, return API info
    return jsonify({
        'status': 'online',
        'name': 'Mighty Raffle Bot API',
        'version': '1.0',
        'message': 'HTML file not found. API endpoints are working.',
        'endpoints': {
            'accounts': {
                'POST /api/accounts': 'Add accounts',
                'GET /api/accounts': 'Get all accounts',
                'POST /api/accounts/clear': 'Clear all accounts'
            },
            'authentication': {
                'POST /api/login': 'Login with credentials',
                'POST /api/turnstile': 'Solve Turnstile captcha'
            },
            'raffles': {
                'GET /api/raffles': 'Get available raffles',
                'POST /api/draw': 'Execute raffle draw',
                'POST /api/check-points': 'Check account points'
            },
            'stats': {
                'GET /api/stats': 'Get server statistics'
            }
        },
        'note': 'Use the mighty_web_app.html file locally and point it to this API URL'
    }), 200

@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

@app.route('/api/accounts', methods=['POST'])
def add_accounts():
    data = request.json
    account_list = data.get('accounts', [])
    
    added = 0
    with accounts_lock:
        for acc in account_list:
            if acc not in accounts:
                accounts.append(acc)
                added += 1
    
    print(f"[ACCOUNTS] Added {added} accounts. Total: {len(accounts)}")
    return jsonify({'success': True, 'accounts': accounts, 'added': added})

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    with accounts_lock:
        return jsonify({'accounts': accounts.copy()})

@app.route('/api/accounts/clear', methods=['POST'])
def clear_accounts():
    with accounts_lock:
        accounts.clear()
    print("[ACCOUNTS] Cleared")
    return jsonify({'success': True})

@app.route('/api/turnstile', methods=['POST'])
def solve_turnstile():
    """Solve Turnstile captcha"""
    if not CAPSOLVER_API_KEY:
        return jsonify({'success': False, 'error': 'API key not configured'}), 400
    
    scraper = get_scraper()
    try:
        # Create task
        response = scraper.post('https://api.capsolver.com/createTask', 
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
            
            result_response = scraper.post('https://api.capsolver.com/getTaskResult',
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
        return_scraper(scraper)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    turnstile_token = data.get('turnstileToken')
    
    if not turnstile_token:
        return jsonify({'success': False, 'message': 'Turnstile token required'}), 400
    
    print(f"[LOGIN] Attempting login for: {username}")
    
    scraper = get_scraper()
    try:
        # More realistic headers
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
            'Sec-Fetch-Site': 'same-site'
        }
        
        payload = {
            'username': username,
            'password': password,
            'cfts_v3': turnstile_token
        }
        
        print(f"[LOGIN] Sending request to Mighty API...")
        
        # Add a small delay to seem more human
        time.sleep(random.uniform(0.5, 1.5))
        
        response = scraper.post('https://be.mighty.ph/api/v1/login',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"[LOGIN] Response status: {response.status_code}")
        
        # Check for Cloudflare challenge
        if response.status_code == 403:
            print(f"[LOGIN] ✗ Cloudflare 403 - Protection triggered")
            return jsonify({'success': False, 'message': 'Cloudflare protection - Try again in a few seconds'}), 403
        
        if response.status_code == 503:
            print(f"[LOGIN] ✗ Service temporarily unavailable")
            return jsonify({'success': False, 'message': 'Service temporarily unavailable'}), 503
        
        text = response.text
        
        # Log first 200 chars for debugging
        print(f"[LOGIN] Response preview: {text[:200]}")
        
        if not text or text.strip() == '':
            return jsonify({'success': False, 'message': 'Empty response from server'}), 500
        
        # Check if response is HTML (Cloudflare challenge page)
        if text.strip().startswith('<') or '<!DOCTYPE' in text or '<html' in text.lower():
            print(f"[LOGIN] ✗ Received HTML instead of JSON - Cloudflare protection")
            return jsonify({'success': False, 'message': 'Cloudflare protection active - Please wait 30 seconds and retry'}), 500
        
        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[LOGIN] ✗ JSON decode error: {e}")
            return jsonify({'success': False, 'message': f'Invalid response format'}), 500
        
        # Success case
        if result.get('code') == 200:
            if result.get('data') and result['data'].get('token'):
                print(f"[LOGIN] ✓ {username} - Login successful!")
                return jsonify({
                    'success': True,
                    'token': result['data']['token'],
                    'user': result['data'].get('user', {})
                })
        
        # Handle error cases
        error_msg = result.get('message', 'Unknown error')
        print(f"[LOGIN] ✗ {username}: {error_msg}")
        
        # Provide user-friendly messages
        if 'not found' in error_msg.lower():
            error_msg = "Account not found - Check username"
        elif 'invalid' in error_msg.lower() or 'incorrect' in error_msg.lower():
            error_msg = "Invalid username or password"
        elif 'turnstile' in error_msg.lower():
            error_msg = "Captcha verification failed - Try again"
        
        return jsonify({'success': False, 'message': error_msg}), 401
            
    except requests.exceptions.Timeout:
        print(f"[LOGIN] ✗ Timeout error")
        return jsonify({'success': False, 'message': 'Request timeout - Server too slow'}), 408
    except requests.exceptions.ConnectionError:
        print(f"[LOGIN] ✗ Connection error")
        return jsonify({'success': False, 'message': 'Connection error - Check internet'}), 503
    except Exception as e:
        print(f"[LOGIN] ✗ Exception: {type(e).__name__}: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    finally:
        return_scraper(scraper)

@app.route('/api/raffles', methods=['GET'])
def get_raffles():
    """Get available raffles - no token required"""
    scraper = get_scraper()
    try:
        response = scraper.get('https://be.mighty.ph/api/v1/raffles',
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
        return_scraper(scraper)

@app.route('/api/draw', methods=['POST'])
def execute_draw():
    data = request.json
    token = data.get('token')
    raffle_id = data.get('raffleId')
    turnstile_token = data.get('turnstileToken')
    
    timestamp = int(time.time() * 1000000000)
    random_part = random.randint(0, 1000000000000)
    browser_id = f"{timestamp:x}{random_part:x}"
    
    scraper = get_scraper()
    try:
        response = scraper.put(f'https://be.mighty.ph/api/v1/raffle/register/{raffle_id}',
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {token}',
                'Origin': 'https://mighty.ph',
                'Referer': 'https://mighty.ph/'
            },
            json={
                'browser_id': browser_id,
                'cfts_v2': turnstile_token
            },
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
        return_scraper(scraper)

@app.route('/api/check-points', methods=['POST'])
def get_points():
    """Check account points"""
    data = request.json
    token = data.get('token')
    
    scraper = get_scraper()
    try:
        response = scraper.get('https://be.mighty.ph/api/v1/user/points',
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
        return_scraper(scraper)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get server statistics"""
    with accounts_lock:
        total_accounts = len(accounts)
    
    return jsonify({
        'status': 'online',
        'totalAccounts': total_accounts,
        'activeThreads': threading.active_count(),
        'scraperPoolSize': len(scrapers),
        'timestamp': time.time()
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'error': 'Not Found',
        'message': 'The requested endpoint does not exist',
        'available_endpoints': [
            'GET /',
            'GET /api/health',
            'GET /api/stats',
            'GET /api/raffles',
            'POST /api/login',
            'POST /api/turnstile',
            'POST /api/draw',
            'POST /api/check-points'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({
        'error': 'Internal Server Error',
        'message': str(e)
    }), 500

# For deployment
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))
    print(f"""
╔═══════════════════════════════════════════════════════╗
║      Mighty Raffle Bot - Production Server           ║
╠═══════════════════════════════════════════════════════╣
║                                                       ║
║  ✓ Multi-threaded (10 workers)                       ║
║  ✓ Connection pooling enabled                        ║
║  ✓ Thread-safe operations                            ║
║  ✓ Optimized for 20-50 accounts                      ║
║  ✓ API Key configured                                ║
║                                                       ║
║  Server: http://0.0.0.0:{port}                       ║
║  API:    http://0.0.0.0:{port}/api                   ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
    """)
    
    # Use production-ready server
    try:
        from waitress import serve
        print("[*] Starting production server with Waitress...")
        serve(app, host='0.0.0.0', port=port, threads=10)
    except ImportError:
        print("[!] Using Flask development server")
        print("[!] Install Waitress for better performance: pip install waitress")
        app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
