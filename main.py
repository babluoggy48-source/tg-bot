#!/usr/bin/env python3
"""
==================================================
MICROWORKERS BOT v2.0.0 - PURE API BASED
Owner: 7977315501
Everything fetched from API - No hardcoding!
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
from datetime import datetime
from typing import Dict, List, Optional, Set, Any
from aiohttp import web

# Telegram
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ==================== CONFIGURATION ====================

OWNER_ID = 7977315501
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')

# API Keys (tumhare diye hue)
API_SECRET_KEY = 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f'
VCODE_SECRET_KEY = '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440'

# API Endpoint (from screenshot)
API_BASE_URL = 'https://api.microworkers.com'  # Current API v2.0.0
API_VERSION = '2.0.0'

# Job Monitoring - Sirf keywords, baaki sab API se
TARGET_KEYWORDS = ['email', 'submit', 'click', 'reply', 'screenshot']  # Sirf ye hardcoded
CHECK_INTERVAL = 45  # seconds

# Web Server
PORT = int(os.environ.get('PORT', 10000))
RENDER_URL = 'https://tg-bot-hmpa.onrender.com'
DATA_FILE = 'users.json'

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== DATA MANAGER ====================

class DataManager:
    """Manage authorized users"""
    
    def __init__(self):
        self.users: Set[int] = {OWNER_ID}
        self.load()
        
    def load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE) as f:
                    data = json.load(f)
                    self.users = set(data.get('users', [])) | {OWNER_ID}
                logger.info(f"📂 Loaded {len(self.users)} users")
        except Exception as e:
            logger.error(f"Load error: {e}")
            
    def save(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump({'users': list(self.users)}, f)
        except Exception as e:
            logger.error(f"Save error: {e}")
            
    def is_owner(self, user_id: int) -> bool:
        return user_id == OWNER_ID
        
    def is_user(self, user_id: int) -> bool:
        return user_id in self.users
        
    def add_user(self, user_id: int) -> bool:
        if user_id not in self.users:
            self.users.add(user_id)
            self.save()
            return True
        return False
        
    def remove_user(self, user_id: int) -> bool:
        if user_id != OWNER_ID and user_id in self.users:
            self.users.remove(user_id)
            self.save()
            return True
        return False
        
    def get_all(self) -> List[int]:
        return list(self.users)

# ==================== API CLIENT v2.0.0 ====================

class MicroWorkersAPI:
    """Pure API Client - Sab kuchh API se aayega"""
    
    def __init__(self):
        self.api_key = API_SECRET_KEY
        self.vcode_key = VCODE_SECRET_KEY
        self.base_url = API_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_count = 0
        self.last_response = None
        
    async def get_session(self) -> aiohttp.ClientSession:
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': f'MicroWorkersBot/{API_VERSION}',
                    'Accept': 'application/json',
                }
            )
        return self.session
        
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            
    def _generate_signatures(self, timestamp: str, method: str, path: str) -> Dict[str, str]:
        """Generate HMAC signatures as per API v2.0.0"""
        payload = f"{timestamp}{method}{path}"
        
        vcode = hmac.new(
            self.vcode_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        auth = hmac.new(
            self.api_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return {
            'X-API-Key': self.api_key,
            'X-VCode': vcode,
            'X-Auth': auth,
            'X-Timestamp': timestamp,
            'Content-Type': 'application/json'
        }
        
    async def get_jobs(self) -> Optional[List[Dict]]:
        """Fetch all jobs from API - PURE API CALL"""
        try:
            session = await self.get_session()
            
            timestamp = str(int(time.time() * 1000))
            path = "/api/v2/jobs?type=all&limit=100"
            
            headers = self._generate_signatures(timestamp, 'GET', path)
            
            url = f"{self.base_url}{path}"
            logger.info(f"🌐 Fetching jobs from API...")
            
            async with session.get(url, headers=headers) as response:
                self.request_count += 1
                
                if response.status == 200:
                    data = await response.json()
                    
                    # API response structure handle karo
                    if isinstance(data, dict):
                        jobs = data.get('jobs', data.get('data', []))
                    else:
                        jobs = data
                        
                    self.last_response = {
                        'time': datetime.now(),
                        'count': len(jobs) if jobs else 0,
                        'status': response.status
                    }
                    
                    logger.info(f"📊 API Response: {len(jobs) if jobs else 0} jobs received")
                    return jobs
                    
                else:
                    error_text = await response.text()
                    logger.error(f"❌ API Error {response.status}: {error_text[:200]}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("⏰ API Timeout")
            return None
        except Exception as e:
            logger.error(f"❌ API Exception: {e}")
            return None
            
    def find_target_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """
        Find jobs matching keywords - PURE API DATA
        Sirf keywords se match karo, baaki sab API se
        """
        if not jobs:
            return []
            
        matched_jobs = []
        
        for job in jobs:
            try:
                # Job title API se lo
                title = str(job.get('title', job.get('name', job.get('description', '')))).lower()
                
                # Check if all keywords present
                if all(keyword in title for keyword in TARGET_KEYWORDS):
                    
                    # Saari values API se lo
                    job_info = {
                        'id': job.get('id', 'N/A'),
                        'title': job.get('title', job.get('name', 'Unknown Job')),
                        'payment': job.get('reward', job.get('payment', '0.00')),
                        'completed': int(job.get('completed_count', job.get('completed', 0))),
                        'total': int(job.get('total_jobs', job.get('total', 0))),
                        'remaining': max(0, int(job.get('total_jobs', job.get('total', 0))) - int(job.get('completed_count', job.get('completed', 0)))),
                        'success_rate': job.get('success_rate', job.get('success_percentage', 'N/A')),
                        'time_to_rate': job.get('time_to_rate', job.get('ttr', 'N/A')),
                        'country_restrictions': job.get('country_restrictions', []),
                        'timestamp': datetime.now().strftime('%d %H:%M')
                    }
                    
                    matched_jobs.append(job_info)
                    logger.info(f"🎯 Found: {job_info['title'][:50]}... | {job_info['completed']}/{job_info['total']}")
                    
            except Exception as e:
                logger.error(f"Error parsing job: {e}")
                continue
                
        return matched_jobs
        
    def get_stats(self) -> Dict:
        """Get API statistics"""
        return {
            'total_requests': self.request_count,
            'last_response': self.last_response,
            'base_url': self.base_url,
            'api_version': API_VERSION
        }

# ==================== BOT ====================

class MicroWorkersBot:
    """Main Bot - Pure API Based"""
    
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.bot = Bot(token=self.token)
        self.data = DataManager()
        self.api = MicroWorkersAPI()
        self.start_time = datetime.now()
        self.stats = {
            'checks': 0,
            'notifications': 0,
            'api_calls': 0,
            'errors': 0
        }
        self.notification_cache = set()
        self.last_job = None
        
    # ========== NOTIFICATION ==========
    
    def format_job_message(self, job: Dict) -> str:
        """Format job notification - PURE API DATA se"""
        
        # Exact screenshot format
        return f"""Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Website: {job['title']} (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Microworkers Alerts
Website: {job['title']} (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}

Website: {job['title']} (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['timestamp']}"""
        
    async def send_to_users(self, text: str, keyboard=None) -> int:
        """Send message to all authorized users"""
        sent = 0
        for user_id in self.data.get_all():
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
                sent += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to send to {user_id}: {e}")
        return sent
        
    async def send_notification(self, job: Dict, is_test: bool = False) -> bool:
        """Send job notification"""
        
        # Cache check for duplicates
        cache_key = f"{job['id']}_{job['completed']}_{job['total']}"
        if not is_test and cache_key in self.notification_cache:
            logger.debug(f"⏳ Duplicate skipped: {job['id']}")
            return False
            
        # Create keyboard with job link
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🚀 OPEN JOB",
                url="https://www.microworkers.com/jobs.php"
            )
        ]])
        
        # Send notification
        message = self.format_job_message(job)
        sent_count = await self.send_to_users(message, keyboard)
        
        if sent_count > 0:
            if not is_test:
                self.notification_cache.add(cache_key)
                self.stats['notifications'] += 1
                self.last_job = job
                
                # Clean cache
                if len(self.notification_cache) > 100:
                    self.notification_cache.clear()
                    
            logger.info(f"✅ Notification sent to {sent_count} users | Job: {job['id']}")
            return True
        else:
            logger.error("❌ Failed to send notification")
            return False
            
    # ========== MONITORING ==========
    
    async def monitor_jobs(self):
        """Main monitoring loop - PURE API"""
        logger.info("🔍 Job monitoring started...")
        
        while True:
            try:
                self.stats['checks'] += 1
                
                # API se jobs lo
                jobs = await self.api.get_jobs()
                self.stats['api_calls'] = self.api.request_count
                
                if jobs:
                    # Target jobs find karo
                    target_jobs = self.api.find_target_jobs(jobs)
                    
                    if target_jobs:
                        logger.info(f"🎯 Found {len(target_jobs)} matching jobs")
                        
                        # Har job ke liye notification bhejo
                        for job in target_jobs:
                            await self.send_notification(job)
                    else:
                        logger.debug("No matching jobs found")
                else:
                    logger.warning("⚠️ No jobs received from API")
                    
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"❌ Monitor error: {e}")
                await asyncio.sleep(60)
                
    # ========== COMMANDS ==========
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        user_id = update.effective_user.id
        
        if not self.data.is_user(user_id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        # API se thoda data dikhao
        jobs = await self.api.get_jobs()
        job_count = len(jobs) if jobs else 0
            
        msg = f"""🚀 *MicroWorkers Bot v{API_VERSION}*

📡 *API Status:*
├ Total Jobs: `{job_count}`
├ API Calls: `{self.api.request_count}`
└ Endpoint: `{API_BASE_URL}`

📌 *Monitoring for keywords:*
`{', '.join(TARGET_KEYWORDS)}`

"""
        if self.data.is_owner(user_id):
            msg += """👑 *Owner Commands*
/users     - List users
/add [id]  - Add user
/remove [id] - Remove user
/broadcast [msg] - Broadcast
/apistats  - API Statistics

"""
            
        msg += """📱 *User Commands*
/status    - Bot status
/test      - Test notification
/jobs      - Show recent jobs
/help      - Help"""
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Status command"""
        user_id = update.effective_user.id
        if not self.data.is_user(user_id):
            return
            
        uptime = datetime.now() - self.start_time
        hours = uptime.total_seconds() / 3600
        
        msg = f"""📊 *Bot Status*

*Runtime*
├ Uptime: `{str(uptime).split('.')[0]}`
├ Checks: `{self.stats['checks']}`
├ Notifications: `{self.stats['notifications']}`
└ Errors: `{self.stats['errors']}`

*API*
├ Calls: `{self.api.request_count}`
├ Jobs/Check: `Fetching...`
└ Rate: `{(self.stats['checks']/max(1, hours)):.1f}/hr`

*System*
├ Users: `{len(self.data.get_all())}`
└ Cache: `{len(self.notification_cache)}`"""
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    async def jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent jobs from API"""
        user_id = update.effective_user.id
        if not self.data.is_user(user_id):
            return
            
        await update.message.reply_text("🔄 Fetching jobs from API...")
        
        jobs = await self.api.get_jobs()
        
        if not jobs:
            await update.message.reply_text("❌ No jobs received from API")
            return
            
        # Target jobs find karo
        target_jobs = self.api.find_target_jobs(jobs)
        
        if target_jobs:
            msg = f"🎯 *Found {len(target_jobs)} Matching Jobs*\n\n"
            for job in target_jobs[:5]:  # Max 5 dikhao
                msg += f"• `${job['payment']}` | {job['completed']}/{job['total']}\n"
                msg += f"  `{job['id']}`\n\n"
        else:
            msg = f"📊 *Total Jobs: {len(jobs)}*\n\nNo matching jobs found right now."
            
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    async def test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test notification"""
        user_id = update.effective_user.id
        if not self.data.is_user(user_id):
            return
            
        # API se real job data lo for test
        jobs = await self.api.get_jobs()
        
        if jobs:
            target_jobs = self.api.find_target_jobs(jobs)
            if target_jobs:
                test_job = target_jobs[0]  # First matching job
            else:
                # Fake job with real API data structure
                test_job = {
                    'id': 'TEST123',
                    'title': 'Email Submit + Click + Reply + Screenshot',
                    'payment': '0.10',
                    'completed': 113,
                    'total': 400,
                    'remaining': 287,
                    'timestamp': datetime.now().strftime('%d %H:%M')
                }
        else:
            # Fake job if API fails
            test_job = {
                'id': 'TEST123',
                'title': 'Email Submit + Click + Reply + Screenshot',
                'payment': '0.10',
                'completed': 113,
                'total': 400,
                'remaining': 287,
                'timestamp': datetime.now().strftime('%d %H:%M')
            }
            
        await update.message.reply_text("🔄 Sending test notification...")
        await self.send_notification(test_job, is_test=True)
        await update.message.reply_text("✅ Test sent!")
        
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""
        user_id = update.effective_user.id
        if not self.data.is_user(user_id):
            return
            
        msg = f"""📚 *Help*

*About*
This bot monitors MicroWorkers API v{API_VERSION}
for jobs containing: `{', '.join(TARGET_KEYWORDS)}`

*How it works*
1. Fetches jobs from API every {CHECK_INTERVAL}s
2. Matches against keywords
3. Sends notification when found

*Commands*
/start  - Welcome
/status - Bot status
/jobs   - Show recent jobs
/test   - Test notification
/help   - This help

*Web Interface*
{RENDER_URL}"""
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        
    # ========== OWNER COMMANDS ==========
    
    async def users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List users"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        msg = "👥 *Authorized Users*\n\n"
        for uid in self.data.get_all():
            msg += f"{'👑 ' if uid == OWNER_ID else '👤 '}`{uid}`\n"
        msg += f"\nTotal: {len(self.data.get_all())}"
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add user"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        if not context.args:
            await update.message.reply_text("❌ Usage: /add [user_id]")
            return
            
        try:
            new_id = int(context.args[0])
            if self.data.add_user(new_id):
                await update.message.reply_text(f"✅ Added `{new_id}`")
                
                # Welcome new user
                try:
                    await self.bot.send_message(
                        chat_id=new_id,
                        text=f"🎉 *Welcome to MicroWorkers Bot!*\n\nYou have been granted access.\nUse /start to begin.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
            else:
                await update.message.reply_text(f"⚠️ User already exists")
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID")
            
    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove user"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        if not context.args:
            await update.message.reply_text("❌ Usage: /remove [user_id]")
            return
            
        try:
            rem_id = int(context.args[0])
            if self.data.remove_user(rem_id):
                await update.message.reply_text(f"✅ Removed `{rem_id}`")
            else:
                await update.message.reply_text(f"⚠️ Cannot remove owner or user not found")
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID")
            
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        if not context.args:
            await update.message.reply_text("❌ Usage: /broadcast [message]")
            return
            
        message = " ".join(context.args)
        await update.message.reply_text(f"🔄 Broadcasting to {len(self.data.get_all())} users...")
        
        sent = await self.send_to_users(f"📢 *Broadcast*\n\n{message}")
        await update.message.reply_text(f"✅ Sent to {sent} users")
        
    async def apistats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """API Statistics"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        api_stats = self.api.get_stats()
        last = api_stats['last_response']
        
        msg = f"""📡 *API Statistics*

*Configuration*
├ Endpoint: `{api_stats['base_url']}`
├ Version: `{api_stats['api_version']}`
└ Total Calls: `{api_stats['total_requests']}`

*Last Response*
{f'├ Time: {last["time"].strftime("%H:%M:%S")}' if last else '├ No response yet'}
{f'├ Jobs: {last["count"]}' if last else '├ Jobs: 0'}
{f'└ Status: {last["status"]}' if last else '└ Status: None'}

*Cache*
└ Notifications: `{len(self.notification_cache)}`"""
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    # ========== RUN ==========
    
    async def run(self):
        """Run the bot"""
        print("\n" + "="*60)
        print("🚀 MICROWORKERS BOT v" + API_VERSION)
        print("="*60)
        print(f"👑 Owner: {OWNER_ID}")
        print(f"📊 Users: {len(self.data.get_all())}")
        print(f"🌐 URL: {RENDER_URL}")
        print(f"📡 API: {API_BASE_URL}")
        print(f"🔍 Keywords: {', '.join(TARGET_KEYWORDS)}")
        print("="*60 + "\n")
        
        # Send startup to owner
        try:
            await self.bot.send_message(
                chat_id=OWNER_ID,
                text=f"""✅ *Bot Started Successfully!*

👑 *Owner:* `{OWNER_ID}`
📊 *Users:* `{len(self.data.get_all())}`
📡 *API:* `{API_BASE_URL}`
🔍 *Keywords:* `{', '.join(TARGET_KEYWORDS)}`
⏱ *Interval:* `{CHECK_INTERVAL}s`
🌐 *Web:* {RENDER_URL}

*Commands Available*
• /users - List users
• /add - Add user
• /remove - Remove user
• /broadcast - Broadcast
• /apistats - API stats""",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            logger.info("✅ Startup message sent to owner")
        except Exception as e:
            logger.error(f"❌ Failed to send startup: {e}")
            
        # Create application
        app = Application.builder().token(self.token).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("jobs", self.jobs))
        app.add_handler(CommandHandler("test", self.test))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("users", self.users))
        app.add_handler(CommandHandler("add", self.add))
        app.add_handler(CommandHandler("remove", self.remove))
        app.add_handler(CommandHandler("broadcast", self.broadcast))
        app.add_handler(CommandHandler("apistats", self.apistats))
        
        # Start monitoring
        asyncio.create_task(self.monitor_jobs())
        
        # Start bot
        logger.info("✅ Bot is running!")
        await app.run_polling(drop_pending_updates=True)

# ==================== WEB SERVER ====================

async def web_server():
    """Web server for Render"""
    app = web.Application()
    
    async def home(request):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>MicroWorkers Bot v{API_VERSION}</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; color: white; }}
                .card {{ background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); border-radius: 20px; padding: 40px; max-width: 600px; }}
                h1 {{ margin: 0; font-size: 2.5em; }}
                .status {{ background: #10b981; display: inline-block; padding: 8px 20px; border-radius: 50px; margin: 20px 0; }}
                code {{ background: rgba(0,0,0,0.3); padding: 3px 8px; border-radius: 5px; }}
                .info {{ margin: 20px 0; }}
                .keywords {{ display: flex; flex-wrap: wrap; gap: 5px; margin: 10px 0; }}
                .keyword {{ background: rgba(255,255,255,0.2); padding: 3px 10px; border-radius: 15px; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🚀 MicroWorkers Bot</h1>
                <div class="status">✅ ONLINE</div>
                
                <div class="info">
                    <p><strong>👑 Owner:</strong> <code>{OWNER_ID}</code></p>
                    <p><strong>📡 API:</strong> <code>{API_BASE_URL}</code> v{API_VERSION}</p>
                    <p><strong>⏱ Interval:</strong> {CHECK_INTERVAL}s</p>
                    <p><strong>🌐 URL:</strong> <code>{RENDER_URL}</code></p>
                    <p><strong>🔍 Keywords:</strong></p>
                    <div class="keywords">
                        {''.join(f'<span class="keyword">{k}</span>' for k in TARGET_KEYWORDS)}
                    </div>
                </div>
                
                <p>
                    <a href="/health" style="color: white;">🔍 Health Check</a> |
                    <a href="https://t.me/thedigamberbot" style="color: white;">📱 Telegram Bot</a>
                </p>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
        
    async def health(request):
        return web.json_response({
            'status': 'ok',
            'api': API_BASE_URL,
            'version': API_VERSION,
            'owner': OWNER_ID
        })
        
    app.router.add_get('/', home)
    app.router.add_get('/health', health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Web server running at {RENDER_URL}")

# ==================== MAIN ====================

async def main():
    """Main entry point"""
    # Start web server
    await web_server()
    
    # Create and run bot
    bot = MicroWorkersBot()
    await bot.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
