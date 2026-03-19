#!/usr/bin/env python3
"""
==================================================
MICROWORKERS ULTIMATE BOT - COMPLETE EDITION
==================================================
Owner: 7977315501
Features: 
- Owner System with Private Commands
- Real-time Job Monitoring
- Screenshot Format Notifications
- Web Interface with Render URL
- User Management (Add/Remove)
- Broadcast System
- Statistics & Status
- API v2.0.0 Compatible
==================================================
"""

import os
import sys
import json
import asyncio
import aiohttp
import hmac
import hashlib
import time
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any, Union
from collections import deque
from aiohttp import web

# Telegram imports
try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.constants import ParseMode
    from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
    from telegram.error import TelegramError, TimedOut, NetworkError
    TELEGRAM_AVAILABLE = True
except ImportError as e:
    print(f"❌ Telegram import error: {e}")
    print("📦 Please install: pip install python-telegram-bot==20.7")
    sys.exit(1)

# ==================================================
# CONFIGURATION
# ==================================================

class Config:
    """Centralized configuration management"""
    
    # Owner Configuration
    OWNER_ID = 7977315501
    
    # Telegram Configuration (from environment)
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
    
    # MicroWorkers API Keys (provided by user)
    API_SECRET_KEY = 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f'
    VCODE_SECRET_KEY = '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440'
    
    # API Settings
    API_BASE_URL = 'https://ttv.microworkers.com'  # Working endpoint
    API_VERSION = '2.0.0'
    API_TIMEOUT = 30
    API_RETRY_COUNT = 3
    
    # Job Monitoring Settings
    TARGET_JOB_KEYWORDS = ['email', 'submit', 'click', 'reply', 'screenshot']
    JOB_PAYMENT = '0.10'
    JOB_NAME = 'Email Submit + Click + Reply + Screenshot'
    CHECK_INTERVAL = 45  # seconds
    NOTIFICATION_COOLDOWN = 300  # 5 minutes
    
    # Web Server Settings
    PORT = int(os.environ.get('PORT', 10000))
    HOST = '0.0.0.0'
    RENDER_URL = 'https://tg-bot-hmpa.onrender.com'
    
    # Data Storage
    DATA_FILE = 'users.json'
    LOG_FILE = 'bot.log'
    ERROR_LOG_FILE = 'errors.log'
    
    # Bot Settings
    MAX_CACHE_SIZE = 100
    MAX_LOG_ENTRIES = 1000
    BOT_VERSION = '2.0.0'
    
    @classmethod
    def validate(cls) -> List[str]:
        """Validate configuration"""
        errors = []
        if not cls.TELEGRAM_TOKEN:
            errors.append("❌ TELEGRAM_TOKEN environment variable not set")
        return errors

# ==================================================
# LOGGING SETUP
# ==================================================

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for better readability"""
    
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    
    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset
        }
        
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

def setup_logging():
    """Setup comprehensive logging system"""
    logger = logging.getLogger('bot')
    logger.setLevel(logging.DEBUG)
    
    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter('%(asctime)s | %(levelname)-8s | %(message)s'))
    logger.addHandler(console_handler)
    
    # File handler for all logs
    try:
        file_handler = logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s'))
        logger.addHandler(file_handler)
    except:
        pass
    
    # Error file handler
    try:
        error_handler = logging.FileHandler(Config.ERROR_LOG_FILE, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s\n%(pathname)s:%(lineno)d\n'))
        logger.addHandler(error_handler)
    except:
        pass
    
    return logger

logger = setup_logging()

# ==================================================
# DATA MANAGER
# ==================================================

class DataManager:
    """
    Manages authorized users and persistent data storage
    Features:
    - Load/save users to JSON file
    - Owner verification
    - User authorization
    - Add/remove users
    """
    
    def __init__(self):
        self.authorized_users: Set[int] = {Config.OWNER_ID}
        self.load()
        logger.info(f"📊 DataManager initialized with {len(self.authorized_users)} users")
        
    def load(self) -> bool:
        """Load authorized users from file"""
        try:
            if os.path.exists(Config.DATA_FILE):
                with open(Config.DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    loaded_users = set(data.get('users', []))
                    self.authorized_users = loaded_users | {Config.OWNER_ID}
                logger.info(f"📂 Loaded {len(self.authorized_users)} users from {Config.DATA_FILE}")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to load data: {e}")
        return False
        
    def save(self) -> bool:
        """Save authorized users to file"""
        try:
            with open(Config.DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'users': list(self.authorized_users),
                    'total': len(self.authorized_users),
                    'updated': datetime.now().isoformat()
                }, f, indent=2)
            logger.debug(f"💾 Saved {len(self.authorized_users)} users to {Config.DATA_FILE}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save data: {e}")
        return False
        
    def is_owner(self, user_id: int) -> bool:
        """Check if user is owner"""
        return user_id == Config.OWNER_ID
        
    def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized"""
        return user_id in self.authorized_users
        
    def add_user(self, user_id: int) -> tuple[bool, str]:
        """
        Add user to authorized list
        Returns: (success, message)
        """
        if user_id in self.authorized_users:
            return False, f"User {user_id} already exists"
        
        self.authorized_users.add(user_id)
        self.save()
        logger.info(f"➕ User {user_id} added by owner")
        return True, f"✅ User {user_id} added successfully"
        
    def remove_user(self, user_id: int) -> tuple[bool, str]:
        """
        Remove user from authorized list
        Returns: (success, message)
        """
        if user_id == Config.OWNER_ID:
            return False, "❌ Cannot remove owner"
        
        if user_id not in self.authorized_users:
            return False, f"User {user_id} not found"
        
        self.authorized_users.remove(user_id)
        self.save()
        logger.info(f"➖ User {user_id} removed by owner")
        return True, f"✅ User {user_id} removed successfully"
        
    def get_all_users(self) -> List[int]:
        """Get list of all authorized users"""
        return sorted(list(self.authorized_users))
        
    def get_user_count(self) -> int:
        """Get total number of authorized users"""
        return len(self.authorized_users)
        
    def get_stats(self) -> Dict:
        """Get data statistics"""
        return {
            'total_users': len(self.authorized_users),
            'owner': Config.OWNER_ID,
            'file': Config.DATA_FILE
        }

# ==================================================
# API CLIENT
# ==================================================

class MicroWorkersAPI:
    """
    MicroWorkers API v2.0.0 Client
    Features:
    - HMAC signature generation
    - Job fetching
    - Target job detection
    - Error handling with retries
    """
    
    def __init__(self):
        self.api_key = Config.API_SECRET_KEY
        self.vcode_key = Config.VCODE_SECRET_KEY
        self.base_url = Config.API_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_count = 0
        self.last_request_time = 0
        self.rate_limit_remaining = 100
        self.rate_limit_reset = 0
        
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': f'MicroWorkersBot/{Config.BOT_VERSION}',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.9',
                },
                timeout=aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
            )
        return self.session
        
    async def close(self):
        """Close session properly"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("🔒 API session closed")
            
    def _generate_signatures(self, timestamp: str, method: str, path: str) -> Dict[str, str]:
        """
        Generate HMAC signatures as per API v2.0.0 documentation
        
        Args:
            timestamp: Current timestamp in milliseconds
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            
        Returns:
            Dictionary with authentication headers
        """
        try:
            payload = f"{timestamp}{method}{path}"
            
            # Generate VCode signature
            vcode = hmac.new(
                self.vcode_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Generate Auth signature
            auth = hmac.new(
                self.api_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            logger.debug(f"🔐 Signatures generated for {method} {path}")
            
            return {
                'X-API-Key': self.api_key,
                'X-VCode': vcode,
                'X-Auth': auth,
                'X-Timestamp': timestamp,
                'Content-Type': 'application/json'
            }
            
        except Exception as e:
            logger.error(f"❌ Signature generation failed: {e}")
            raise
            
    async def get_jobs(self, retry_count: int = 0) -> Optional[List[Dict]]:
        """
        Fetch jobs from API with retry logic
        
        Args:
            retry_count: Current retry attempt number
            
        Returns:
            List of jobs or None on failure
        """
        try:
            session = await self.get_session()
            
            # Rate limiting check
            current_time = time.time()
            if current_time - self.last_request_time < 1.0:
                await asyncio.sleep(1.0)
                
            timestamp = str(int(time.time() * 1000))
            path = "/api/v2/jobs?type=all&limit=100"
            
            headers = self._generate_signatures(timestamp, 'GET', path)
            
            url = f"{self.base_url}{path}"
            logger.debug(f"🌐 Fetching jobs from: {url}")
            
            start_time = time.time()
            async with session.get(url, headers=headers) as response:
                self.last_request_time = time.time()
                self.request_count += 1
                
                # Track rate limits
                self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 100))
                self.rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
                
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    jobs = data.get('jobs') if isinstance(data, dict) else data
                    
                    if jobs is not None:
                        logger.info(f"📊 API #{self.request_count} | Status: 200 | Jobs: {len(jobs)} | Time: {response_time:.2f}s")
                        return jobs
                    else:
                        logger.warning(f"⚠️ API returned success but no jobs data")
                        return []
                        
                elif response.status == 401:
                    logger.error(f"❌ API Authentication failed - Check API keys")
                    return None
                    
                elif response.status == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"⏳ Rate limited. Waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    if retry_count < Config.API_RETRY_COUNT:
                        return await self.get_jobs(retry_count + 1)
                    return None
                    
                elif response.status == 404:
                    logger.error(f"❌ API 404: Endpoint not found - Check API_BASE_URL")
                    return None
                    
                else:
                    error_text = await response.text()
                    logger.error(f"❌ API Error {response.status}: {error_text[:200]}")
                    
                    if retry_count < Config.API_RETRY_COUNT:
                        wait_time = 2 ** retry_count
                        logger.info(f"🔄 Retrying in {wait_time}s... (Attempt {retry_count + 1}/{Config.API_RETRY_COUNT})")
                        await asyncio.sleep(wait_time)
                        return await self.get_jobs(retry_count + 1)
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"⏰ API Timeout after {Config.API_TIMEOUT}s")
            if retry_count < Config.API_RETRY_COUNT:
                wait_time = 2 ** retry_count
                logger.info(f"🔄 Retrying in {wait_time}s... (Attempt {retry_count + 1}/{Config.API_RETRY_COUNT})")
                await asyncio.sleep(wait_time)
                return await self.get_jobs(retry_count + 1)
            return None
            
        except aiohttp.ClientError as e:
            logger.error(f"🌐 Network error: {e}")
            if retry_count < Config.API_RETRY_COUNT:
                wait_time = 2 ** retry_count
                logger.info(f"🔄 Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                return await self.get_jobs(retry_count + 1)
            return None
            
        except Exception as e:
            logger.error(f"❌ Unexpected API error: {e}")
            logger.debug(traceback.format_exc())
            return None
            
    def find_target_job(self, jobs: List[Dict]) -> Optional[Dict]:
        """
        Find our target job in the jobs list
        
        Args:
            jobs: List of jobs from API
            
        Returns:
            Job details dictionary or None if not found
        """
        if not jobs:
            return None
            
        found_jobs = []
        
        for job in jobs:
            try:
                # Get job title from various possible fields
                title = str(job.get('title', job.get('name', job.get('description', '')))).lower()
                
                # Check if all keywords are present
                if all(keyword in title for keyword in Config.TARGET_JOB_KEYWORDS):
                    
                    # Safely extract numeric values
                    completed = self._safe_int(job.get('completed_count', job.get('completed', 0)))
                    total = self._safe_int(job.get('total_jobs', job.get('total', 100)))
                    remaining = max(0, total - completed)
                    
                    job_info = {
                        'id': job.get('id', 'unknown'),
                        'name': Config.JOB_NAME,
                        'payment': Config.JOB_PAYMENT,
                        'completed': completed,
                        'total': total,
                        'remaining': remaining,
                        'timestamp': datetime.now().strftime('%d %H:%M'),
                        'success_rate': job.get('success_rate', 'N/A'),
                        'ttr': job.get('time_to_rate', job.get('ttr', 'N/A')),
                        'country_restrictions': job.get('country_restrictions', []),
                        'requirements': job.get('requirements', {})
                    }
                    
                    found_jobs.append(job_info)
                    logger.debug(f"🎯 Found target job: {completed}/{total} completed")
                    
            except Exception as e:
                logger.error(f"Error parsing job: {e}")
                continue
                
        # Return the most recent job (highest completion)
        if found_jobs:
            return max(found_jobs, key=lambda x: x['completed'])
        return None
        
    def _safe_int(self, value: Any, default: int = 0) -> int:
        """Safely convert value to integer"""
        try:
            if value is None:
                return default
            return int(float(value))
        except (ValueError, TypeError):
            return default
            
    def get_stats(self) -> Dict:
        """Get API statistics"""
        return {
            'request_count': self.request_count,
            'rate_limit_remaining': self.rate_limit_remaining,
            'rate_limit_reset': self.rate_limit_reset,
            'base_url': self.base_url
        }

# ==================================================
# WEB SERVER
# ==================================================

class WebServer:
    """
    Web server for Render health checks and status page
    Features:
    - Beautiful status page with Render URL
    - Health check endpoint
    - Live statistics display
    """
    
    def __init__(self, bot: 'MicroWorkersBot'):
        self.bot = bot
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.setup_routes()
        
    def setup_routes(self):
        """Setup all web routes"""
        self.app.router.add_get('/', self.home_page)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/stats', self.stats_json)
        self.app.router.add_get('/status', self.status_page)
        
    async def home_page(self, request: web.Request) -> web.Response:
        """Beautiful home page with bot status"""
        uptime = datetime.now() - self.bot.start_time
        hours = uptime.total_seconds() / 3600
        
        # Get bot username
        bot_username = "your_bot"
        try:
            me = await self.bot.bot.get_me()
            bot_username = me.username
        except:
            pass
            
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MicroWorkers Ultimate Bot</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1000px;
            width: 100%;
        }}
        
        .card {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        
        .header h1 {{
            font-size: 3em;
            color: #333;
            margin-bottom: 10px;
        }}
        
        .header p {{
            color: #666;
            font-size: 1.1em;
        }}
        
        .status-badge {{
            display: inline-block;
            padding: 10px 30px;
            background: #10b981;
            color: white;
            border-radius: 50px;
            font-weight: bold;
            font-size: 1.2em;
            margin: 20px 0;
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        
        .stat-item {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            transition: transform 0.3s;
        }}
        
        .stat-item:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin: 10px 0;
        }}
        
        .stat-unit {{
            color: #999;
            font-size: 0.9em;
        }}
        
        .info-box {{
            background: #f0f4ff;
            border-radius: 15px;
            padding: 25px;
            margin: 30px 0;
        }}
        
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid #e0e7ff;
        }}
        
        .info-row:last-child {{
            border-bottom: none;
        }}
        
        .info-label {{
            color: #4b5563;
            font-weight: 500;
        }}
        
        .info-value {{
            color: #1f2937;
            font-family: 'Courier New', monospace;
            font-weight: 600;
        }}
        
        .url-box {{
            background: #1f2937;
            border-radius: 10px;
            padding: 15px;
            margin: 20px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .url-text {{
            color: #10b981;
            font-family: 'Courier New', monospace;
            font-size: 1.1em;
        }}
        
        .copy-btn {{
            background: #10b981;
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            transition: background 0.3s;
        }}
        
        .copy-btn:hover {{
            background: #059669;
        }}
        
        .commands {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minass(150px, 1fr));
            gap: 10px;
            margin-top: 20px;
        }}
        
        .command {{
            background: #e5e7eb;
            padding: 8px 15px;
            border-radius: 20px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            color: #374151;
            text-align: center;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 40px;
            color: #6b7280;
            font-size: 0.9em;
        }}
        
        .footer a {{
            color: #667eea;
            text-decoration: none;
        }}
        
        .footer a:hover {{
            text-decoration: underline;
        }}
        
        @media (max-width: 768px) {{
            .card {{
                padding: 20px;
            }}
            
            .header h1 {{
                font-size: 2em;
            }}
            
            .stat-value {{
                font-size: 2em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>🚀 MicroWorkers Ultimate Bot</h1>
                <p>Real-time job monitoring & notifications</p>
                <div class="status-badge">🟢 ONLINE</div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-label">Uptime</div>
                    <div class="stat-value">{str(uptime).split('.')[0]}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">API Checks</div>
                    <div class="stat-value">{self.bot.stats['checks']}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Notifications</div>
                    <div class="stat-value">{self.bot.stats['notifications']}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Users</div>
                    <div class="stat-value">{self.bot.data.get_user_count()}</div>
                </div>
            </div>
            
            <div class="info-box">
                <h3 style="margin-bottom: 20px; color: #374151;">📋 Bot Information</h3>
                
                <div class="info-row">
                    <span class="info-label">👑 Owner ID</span>
                    <span class="info-value"><code>{Config.OWNER_ID}</code></span>
                </div>
                
                <div class="info-row">
                    <span class="info-label">📌 Monitoring</span>
                    <span class="info-value">{Config.JOB_NAME}</span>
                </div>
                
                <div class="info-row">
                    <span class="info-label">⏱ Check Interval</span>
                    <span class="info-value">{Config.CHECK_INTERVAL} seconds</span>
                </div>
                
                <div class="info-row">
                    <span class="info-label">📡 API Version</span>
                    <span class="info-value">v{Config.API_VERSION}</span>
                </div>
                
                <div class="info-row">
                    <span class="info-label">🤖 Bot Version</span>
                    <span class="info-value">v{Config.BOT_VERSION}</span>
                </div>
                
                <div class="info-row">
                    <span class="info-label">📊 API Calls</span>
                    <span class="info-value">{self.bot.api.request_count}</span>
                </div>
            </div>
            
            <div class="url-box">
                <span class="url-text" id="renderUrl">{Config.RENDER_URL}</span>
                <button class="copy-btn" onclick="copyUrl()">Copy URL</button>
            </div>
            
            <h3 style="margin: 20px 0; color: #374151;">🤖 Available Commands</h3>
            
            <div class="commands">
                <span class="command">/start</span>
                <span class="command">/status</span>
                <span class="command">/stats</span>
                <span class="command">/test</span>
                <span class="command">/help</span>
                <span class="command">/users</span>
                <span class="command">/add</span>
                <span class="command">/remove</span>
                <span class="command">/broadcast</span>
            </div>
            
            <div style="margin-top: 30px;">
                <p><strong>📱 Telegram Bot:</strong> <a href="https://t.me/{bot_username}" target="_blank">@{bot_username}</a></p>
                <p><strong>🔗 Callback URL:</strong> <code>{Config.RENDER_URL}/callback</code></p>
            </div>
            
            <div class="footer">
                <p>Made with ❤️ for MicroWorkers | <a href="/health">Health Check</a> | <a href="/stats">JSON Stats</a></p>
                <p>© 2026 MicroWorkers Ultimate Bot</p>
            </div>
        </div>
    </div>
    
    <script>
        function copyUrl() {{
            var url = document.getElementById('renderUrl').innerText;
            navigator.clipboard.writeText(url).then(function() {{
                var btn = document.querySelector('.copy-btn');
                btn.innerText = 'Copied!';
                btn.style.background = '#059669';
                setTimeout(function() {{
                    btn.innerText = 'Copy URL';
                    btn.style.background = '#10b981';
                }}, 2000);
            }});
        }}
    </script>
</body>
</html>"""
        
        return web.Response(text=html, content_type='text/html')
        
    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint for Render"""
        return web.json_response({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'uptime': str(datetime.now() - self.bot.start_time),
            'owner': Config.OWNER_ID,
            'version': Config.BOT_VERSION
        })
        
    async def stats_json(self, request: web.Request) -> web.Response:
        """JSON statistics endpoint"""
        uptime = datetime.now() - self.bot.start_time
        
        return web.json_response({
            'status': 'online',
            'owner': Config.OWNER_ID,
            'uptime': str(uptime),
            'uptime_seconds': uptime.total_seconds(),
            'stats': self.bot.stats,
            'users': {
                'total': self.bot.data.get_user_count(),
                'list': self.bot.data.get_all_users()
            },
            'api': self.bot.api.get_stats(),
            'config': {
                'check_interval': Config.CHECK_INTERVAL,
                'job': Config.JOB_NAME,
                'api_version': Config.API_VERSION,
                'bot_version': Config.BOT_VERSION,
                'render_url': Config.RENDER_URL
            }
        })
        
    async def status_page(self, request: web.Request) -> web.Response:
        """Simple status page"""
        uptime = datetime.now() - self.bot.start_time
        
        html = f"""
        <html>
        <head><title>Bot Status</title></head>
        <body style="font-family: Arial; padding: 40px;">
            <h1>🤖 MicroWorkers Bot Status</h1>
            <p>✅ Online</p>
            <p>Uptime: {str(uptime).split('.')[0]}</p>
            <p>Checks: {self.bot.stats['checks']}</p>
            <p>Notifications: {self.bot.stats['notifications']}</p>
            <p><a href="/">Back to Home</a></p>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
        
    async def start(self):
        """Start the web server"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, Config.HOST, Config.PORT)
        await site.start()
        logger.info(f"🌐 Web server running at {Config.RENDER_URL}")
        
    async def stop(self):
        """Stop the web server"""
        if self.runner:
            await self.runner.cleanup()
            logger.info("🛑 Web server stopped")

# ==================================================
# TELEGRAM BOT
# ==================================================

class MicroWorkersBot:
    """
    Main Telegram Bot Class
    Features:
    - Owner system with private commands
    - User authorization
    - Job monitoring
    - Notification system
    - Statistics tracking
    - Command handlers
    """
    
    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.bot = Bot(token=self.token)
        self.data = DataManager()
        self.api = MicroWorkersAPI()
        self.web = WebServer(self)
        self.application: Optional[Application] = None
        
        # Bot statistics
        self.start_time = datetime.now()
        self.stats = {
            'checks': 0,
            'notifications': 0,
            'errors': 0,
            'commands_processed': 0,
            'messages_sent': 0
        }
        
        # Notification cache
        self.notification_cache = deque(maxlen=Config.MAX_CACHE_SIZE)
        self.callback_logs = deque(maxlen=100)
        
        logger.info("🤖 Bot instance created")
        
    # ==================================================
    # AUTHENTICATION & AUTHORIZATION
    # ==================================================
    
    async def check_auth(self, update: Update) -> bool:
        """
        Check if user is authorized to use the bot
        Sends unauthorized message if not
        """
        user = update.effective_user
        if not user:
            return False
            
        user_id = user.id
        username = user.username or "No username"
        
        if self.data.is_authorized(user_id):
            logger.debug(f"✅ Authorized access: {user_id} (@{username})")
            return True
            
        # Unauthorized access
        logger.warning(f"⚠️ Unauthorized access attempt: {user_id} (@{username})")
        
        try:
            await update.message.reply_text(
                "❌ *Unauthorized Access*\n\n"
                "You are not authorized to use this bot.\n"
                f"If you believe this is a mistake, contact the owner.\n\n"
                f"Your ID: `{user_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
            
        return False
        
    def is_owner(self, user_id: int) -> bool:
        """Check if user is owner"""
        return self.data.is_owner(user_id)
        
    # ==================================================
    # NOTIFICATION SYSTEM
    # ==================================================
    
    def format_job_message(self, job: Dict) -> str:
        """
        Format job notification exactly like the screenshot
        """
        return f"""Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Microworkers Alerts
Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}"""
        
    async def send_to_all_users(self, text: str, keyboard: Optional[InlineKeyboardMarkup] = None) -> int:
        """
        Send message to all authorized users
        Returns number of successful sends
        """
        sent_count = 0
        failed_count = 0
        
        for user_id in self.data.get_all_users():
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
                sent_count += 1
                self.stats['messages_sent'] += 1
                await asyncio.sleep(0.1)  # Rate limiting
                
            except TelegramError as e:
                failed_count += 1
                logger.error(f"❌ Failed to send to {user_id}: {e}")
                
        logger.debug(f"📨 Sent to {sent_count} users ({failed_count} failed)")
        return sent_count
        
    async def send_notification(self, job: Dict, is_test: bool = False) -> bool:
        """
        Send job notification to all users
        Returns True if notification was sent
        """
        # Check cache for duplicates (skip for test)
        if not is_test:
            cache_key = f"{job['completed']}_{job['total']}"
            if cache_key in self.notification_cache:
                logger.debug(f"⏳ Duplicate notification skipped: {cache_key}")
                return False
                
        # Create keyboard
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🚀 OPEN JOB",
                url="https://www.microworkers.com/jobs.php"
            )
        ]])
        
        # Format and send message
        message = self.format_job_message(job)
        sent_count = await self.send_to_all_users(message, keyboard)
        
        if sent_count > 0:
            if not is_test:
                cache_key = f"{job['completed']}_{job['total']}"
                self.notification_cache.append(cache_key)
                self.stats['notifications'] += 1
                
            logger.info(f"✅ Notification sent to {sent_count} users | {job['completed']}/{job['total']}")
            return True
        else:
            logger.error("❌ Failed to send notification to any user")
            return False
            
    # ==================================================
    # JOB MONITORING
    # ==================================================
    
    async def monitor_jobs(self):
        """
        Main monitoring loop - runs continuously
        """
        logger.info("🔍 Job monitoring loop started")
        
        while True:
            try:
                self.stats['checks'] += 1
                
                # Fetch jobs from API
                jobs = await self.api.get_jobs()
                
                if jobs:
                    # Find target job
                    target_job = self.api.find_target_job(jobs)
                    
                    if target_job:
                        logger.info(f"🎯 Target job found: {target_job['completed']}/{target_job['total']} completed")
                        await self.send_notification(target_job)
                    else:
                        logger.debug("No target job found in this batch")
                else:
                    logger.warning("⚠️ No jobs received from API")
                    
                # Wait before next check
                await asyncio.sleep(Config.CHECK_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("🛑 Monitoring loop cancelled")
                break
                
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"❌ Monitoring error: {e}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(60)  # Wait 1 minute on error
                
    # ==================================================
    # COMMAND HANDLERS - PUBLIC
    # ==================================================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command - welcome message with commands"""
        if not await self.check_auth(update):
            return
            
        self.stats['commands_processed'] += 1
        user_id = update.effective_user.id
        is_owner = self.is_owner(user_id)
        
        # Build message based on user type
        message = f"""🚀 *MicroWorkers Ultimate Bot*

*Bot Information*
├ 📌 *Monitoring:* `{Config.JOB_NAME}`
├ ⏱ *Interval:* `{Config.CHECK_INTERVAL}s`
├ 👥 *Users:* `{self.data.get_user_count()}`
├ 🌐 *Web:* [{Config.RENDER_URL}]({Config.RENDER_URL})
└ 📡 *API:* v{Config.API_VERSION}

"""
        if is_owner:
            message += """👑 *Owner Commands*
/users     - List all authorized users
/add [id]  - Add new user
/remove [id] - Remove user
/broadcast [msg] - Broadcast message
/stats     - Detailed statistics

"""
            
        message += """📱 *User Commands*
/status    - Bot status
/test      - Send test notification
/help      - Show this help

💡 *The bot will automatically notify you when the target job is available!*
"""
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Status command - show bot status"""
        if not await self.check_auth(update):
            return
            
        self.stats['commands_processed'] += 1
        
        uptime = datetime.now() - self.start_time
        hours = uptime.total_seconds() / 3600
        
        message = f"""📊 *Bot Status Report*

*Runtime Information*
├ 🕒 *Uptime:* `{str(uptime).split('.')[0]}`
├ 🔄 *API Checks:* `{self.stats['checks']}`
├ 📨 *Notifications:* `{self.stats['notifications']}`
├ 📊 *Checks/Hour:* `{(self.stats['checks']/max(1, hours)):.1f}`
└ ❌ *Errors:* `{self.stats['errors']}`

*System Information*
├ 👥 *Users:* `{self.data.get_user_count()}`
├ ⏱ *Check Interval:* `{Config.CHECK_INTERVAL}s`
├ 📡 *API Calls:* `{self.api.request_count}`
└ 🌐 *Web:* [{Config.RENDER_URL}]({Config.RENDER_URL})

*Last Notification*
{cache_info if (cache_info := self._get_last_notification()) else '├ No notifications yet'}"""
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    def _get_last_notification(self) -> str:
        """Get last notification info"""
        if not self.notification_cache:
            return ""
        last = self.notification_cache[-1]
        return f"├ 🎯 `{last}`"
        
    async def cmd_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test command - send test notification"""
        if not await self.check_auth(update):
            return
            
        self.stats['commands_processed'] += 1
        
        test_job = {
            'payment': Config.JOB_PAYMENT,
            'completed': 113,
            'total': 400,
            'remaining': 287,
            'timestamp': datetime.now().strftime('%d %H:%M')
        }
        
        await update.message.reply_text("🔄 Sending test notification to all users...")
        sent = await self.send_notification(test_job, is_test=True)
        
        if sent:
            await update.message.reply_text("✅ Test notification sent successfully!")
        else:
            await update.message.reply_text("❌ Failed to send test notification")
            
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command - show available commands"""
        if not await self.check_auth(update):
            return
            
        self.stats['commands_processed'] += 1
        user_id = update.effective_user.id
        is_owner = self.is_owner(user_id)
        
        message = f"""📚 *Command Reference*

*Basic Commands*
/start    - Welcome and command list
/status   - Show bot status
/test     - Send test notification
/help     - Show this help

*About*
This bot monitors MicroWorkers for:
`{Config.JOB_NAME}`

When the job becomes available, you'll receive a notification with the exact format shown in the screenshot.

*Web Interface*
🌐 {Config.RENDER_URL}

*Support*
For issues or to request access, contact the bot owner.
"""
        
        if is_owner:
            message += """

*Owner Commands*
/users     - List all users
/add <id>  - Add new user
/remove <id> - Remove user
/broadcast <msg> - Broadcast to all users
/stats     - Detailed statistics"""
            
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    # ==================================================
    # COMMAND HANDLERS - OWNER ONLY
    # ==================================================
    
    async def cmd_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all authorized users - Owner only"""
        user_id = update.effective_user.id
        
        if not self.is_owner(user_id):
            await update.message.reply_text("❌ This command is only available for the bot owner.")
            return
            
        self.stats['commands_processed'] += 1
        
        users = self.data.get_all_users()
        
        message = f"""👥 *Authorized Users* (Total: {len(users)})

"""
        for uid in users:
            if uid == Config.OWNER_ID:
                message += f"👑 `{uid}` (Owner)\n"
            else:
                message += f"👤 `{uid}`\n"
                
        message += f"\n📍 *Owner ID:* `{Config.OWNER_ID}`"
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )
        
    async def cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add new user - Owner only"""
        user_id = update.effective_user.id
        
        if not self.is_owner(user_id):
            await update.message.reply_text("❌ This command is only available for the bot owner.")
            return
            
        self.stats['commands_processed'] += 1
        
        # Check if user ID provided
        if not context.args:
            await update.message.reply_text(
                "❌ *Usage:* `/add [user_id]`\n\n"
                "Example: `/add 123456789`\n\n"
                "💡 Get user ID from @userinfobot",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        try:
            new_user_id = int(context.args[0])
            success, message = self.data.add_user(new_user_id)
            
            if success:
                # Send welcome message to new user
                try:
                    await self.bot.send_message(
                        chat_id=new_user_id,
                        text=f"""🎉 *Welcome to MicroWorkers Bot!*

You have been granted access by the owner.

*Commands:*
/start - Get started
/status - Check bot status
/test - Test notification

📍 *Owner ID:* `{Config.OWNER_ID}`
🌐 *Web:* {Config.RENDER_URL}""",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                    message += "\n📨 Welcome message sent to new user"
                except:
                    message += "\n⚠️ Could not send welcome message"
                    
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a valid numeric ID.")
            
    async def cmd_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove user - Owner only"""
        user_id = update.effective_user.id
        
        if not self.is_owner(user_id):
            await update.message.reply_text("❌ This command is only available for the bot owner.")
            return
            
        self.stats['commands_processed'] += 1
        
        if not context.args:
            await update.message.reply_text(
                "❌ *Usage:* `/remove [user_id]`\n\n"
                "Example: `/remove 123456789`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        try:
            remove_id = int(context.args[0])
            success, message = self.data.remove_user(remove_id)
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a valid numeric ID.")
            
    async def cmd_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users - Owner only"""
        user_id = update.effective_user.id
        
        if not self.is_owner(user_id):
            await update.message.reply_text("❌ This command is only available for the bot owner.")
            return
            
        self.stats['commands_processed'] += 1
        
        if not context.args:
            await update.message.reply_text(
                "❌ *Usage:* `/broadcast [message]`\n\n"
                "Example: `/broadcast Hello everyone!`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        message = " ".join(context.args)
        broadcast_msg = f"📢 *Broadcast from Owner*\n\n{message}"
        
        # Send to owner first as confirmation
        await update.message.reply_text(f"🔄 Broadcasting to {self.data.get_user_count()} users...")
        
        sent_count = await self.send_to_all_users(broadcast_msg)
        
        await update.message.reply_text(
            f"✅ Broadcast complete!\n"
            f"📨 Sent to: {sent_count} users\n"
            f"❌ Failed: {self.data.get_user_count() - sent_count} users"
        )
        
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Detailed statistics - Owner only"""
        user_id = update.effective_user.id
        
        if not self.is_owner(user_id):
            await update.message.reply_text("❌ This command is only available for the bot owner.")
            return
            
        self.stats['commands_processed'] += 1
        
        uptime = datetime.now() - self.start_time
        hours = uptime.total_seconds() / 3600
        api_stats = self.api.get_stats()
        
        message = f"""📊 *Detailed Statistics*

*Bot Runtime*
├ 🕒 *Started:* `{self.start_time.strftime('%Y-%m-%d %H:%M:%S')}`
├ ⏱ *Uptime:* `{str(uptime).split('.')[0]}`
├ 📈 *Uptime Hours:* `{hours:.2f}h`
└ 🔄 *Commands:* `{self.stats['commands_processed']}`

*Performance*
├ 🔍 *API Checks:* `{self.stats['checks']}`
├ 📨 *Notifications:* `{self.stats['notifications']}`
├ 📊 *Checks/Hour:* `{(self.stats['checks']/max(1, hours)):.1f}`
├ 📨 *Notifs/Hour:* `{(self.stats['notifications']/max(1, hours)):.1f}`
└ ❌ *Errors:* `{self.stats['errors']}`

*API Statistics*
├ 📞 *Total Calls:* `{api_stats['request_count']}`
├ 🎯 *Rate Limit:* `{api_stats['rate_limit_remaining']}` remaining
└ 🌐 *Endpoint:* `{api_stats['base_url']}`

*User Management*
├ 👥 *Total Users:* `{self.data.get_user_count()}`
├ 👑 *Owner:* `{Config.OWNER_ID}`
└ 📁 *Data File:* `{Config.DATA_FILE}`

*Cache Status*
├ 💾 *Notification Cache:* `{len(self.notification_cache)}/{Config.MAX_CACHE_SIZE}`
└ 🎯 *Last Job:* `{self._get_last_notification() or 'None'}`

*System*
├ 🤖 *Bot Version:* `v{Config.BOT_VERSION}`
├ 📡 *API Version:* `v{Config.API_VERSION}`
├ ⏱ *Check Interval:* `{Config.CHECK_INTERVAL}s`
└ 🌐 *Web:* [{Config.RENDER_URL}]({Config.RENDER_URL})"""
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    # ==================================================
    # BOT LIFECYCLE
    # ==================================================
    
    async def initialize(self):
        """Initialize bot components"""
        logger.info("🔄 Initializing bot components...")
        
        # Verify configuration
        errors = Config.validate()
        if errors:
            for error in errors:
                logger.error(error)
            return False
            
        # Test Telegram connection
        try:
            me = await self.bot.get_me()
            logger.info(f"✅ Connected to Telegram as @{me.username}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Telegram: {e}")
            return False
            
        # Send startup message to owner
        try:
            uptime = datetime.now() - self.start_time
            await self.bot.send_message(
                chat_id=Config.OWNER_ID,
                text=f"""✅ *Bot Started Successfully!*

👑 *Owner:* `{Config.OWNER_ID}`
📊 *Users:* `{self.data.get_user_count()}`
⏱ *Interval:* `{Config.CHECK_INTERVAL}s`
📡 *API:* v{Config.API_VERSION}
🤖 *Version:* v{Config.BOT_VERSION}
🌐 *Web:* [{Config.RENDER_URL}]({Config.RENDER_URL})

📌 *Monitoring:* `{Config.JOB_NAME}`

*Owner Commands Available*
• /users - List users
• /add - Add user
• /remove - Remove user
• /broadcast - Broadcast
• /stats - Detailed stats""",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            logger.info("✅ Startup message sent to owner")
        except Exception as e:
            logger.error(f"❌ Failed to send startup message: {e}")
            
        return True
        
    async def run(self):
        """Main run method"""
        print("\n" + "="*60)
        print("🚀 MICROWORKERS ULTIMATE BOT v" + Config.BOT_VERSION)
        print("="*60)
        print(f"👑 Owner ID: {Config.OWNER_ID}")
        print(f"📊 Authorized Users: {self.data.get_user_count()}")
        print(f"🌐 Web URL: {Config.RENDER_URL}")
        print(f"⏱ Check Interval: {Config.CHECK_INTERVAL}s")
        print(f"📡 API Version: v{Config.API_VERSION}")
        print("="*60 + "\n")
        
        # Initialize bot
        if not await self.initialize():
            logger.error("❌ Bot initialization failed")
            return
            
        # Start web server
        await self.web.start()
        
        # Create application
        self.application = Application.builder().token(self.token).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("test", self.cmd_test))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        
        # Owner-only handlers
        self.application.add_handler(CommandHandler("users", self.cmd_users))
        self.application.add_handler(CommandHandler("add", self.cmd_add))
        self.application.add_handler(CommandHandler("remove", self.cmd_remove))
        self.application.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        self.application.add_handler(CommandHandler("stats", self.cmd_stats))
        
        # Start monitoring in background
        asyncio.create_task(self.monitor_jobs())
        
        # Start bot
        logger.info("✅ Bot is fully operational!")
        await self.application.run_polling(drop_pending_updates=True)

# ==================================================
# MAIN ENTRY POINT
# ==================================================

async def main():
    """Main entry point"""
    try:
        # Validate configuration first
        errors = Config.validate()
        if errors:
            for error in errors:
                logger.error(error)
            logger.error("❌ Configuration errors found. Please fix and redeploy.")
            return
            
        # Create and run bot
        bot = MicroWorkersBot()
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal error in main: {e}")
        logger.debug(traceback.format_exc())
        # Keep the process alive for Render
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Unhandled exception: {e}")
        traceback.print_exc()
