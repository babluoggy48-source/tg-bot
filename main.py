#!/usr/bin/env python3
"""
MicroWorkers BOT - PROPER WORKING VERSION
Owner: 7977315501
Render URL: https://tg-bot-hmpa.onrender.com
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
from typing import Dict, List, Optional, Set
from aiohttp import web

# Telegram
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

# ==================== CONFIG ====================

OWNER_ID = 7977315501
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
API_SECRET_KEY = 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f'
VCODE_SECRET_KEY = '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440'
API_BASE_URL = 'https://ttv.microworkers.com'
CHECK_INTERVAL = 45
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
    def __init__(self):
        self.users: Set[int] = {OWNER_ID}
        self.load()
        
    def load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.users = set(data.get('users', []))
                    self.users.add(OWNER_ID)
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
        
    def get_users(self) -> List[int]:
        return list(self.users)

# ==================== API CLIENT ====================

class MicroWorkersAPI:
    def __init__(self):
        self.api_key = API_SECRET_KEY
        self.vcode_key = VCODE_SECRET_KEY
        self.base_url = API_BASE_URL
        self.session = None
        
    async def get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
        
    async def close(self):
        if self.session:
            await self.session.close()
            
    def _sign(self, timestamp: str, method: str, path: str) -> Dict:
        payload = f"{timestamp}{method}{path}"
        vcode = hmac.new(self.vcode_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        auth = hmac.new(self.api_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return {
            'X-API-Key': self.api_key,
            'X-VCode': vcode,
            'X-Auth': auth,
            'X-Timestamp': timestamp
        }
        
    async def get_jobs(self):
        try:
            session = await self.get_session()
            timestamp = str(int(time.time() * 1000))
            path = '/api/v2/jobs?type=all&limit=100'
            headers = self._sign(timestamp, 'GET', path)
            headers['Content-Type'] = 'application/json'
            
            async with session.get(f"{self.base_url}{path}", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    jobs = data.get('jobs') if isinstance(data, dict) else data
                    if jobs:
                        logger.info(f"📊 Got {len(jobs)} jobs from API")
                    return jobs
                else:
                    logger.warning(f"API status: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"API error: {e}")
            return None
            
    def find_job(self, jobs):
        if not jobs:
            return None
            
        keywords = ['email', 'submit', 'click', 'reply', 'screenshot']
        
        for job in jobs:
            try:
                title = str(job.get('title', job.get('name', ''))).lower()
                
                if all(k in title for k in keywords):
                    completed = int(job.get('completed_count', job.get('completed', 0)))
                    total = int(job.get('total_jobs', job.get('total', 100)))
                    
                    logger.info(f"🎯 Found target job: {completed}/{total}")
                    
                    return {
                        'payment': '0.10',
                        'completed': completed,
                        'total': total,
                        'remaining': total - completed,
                        'time': datetime.now().strftime('%d %H:%M')
                    }
            except:
                continue
                
        return None

# ==================== BOT ====================

class MicroWorkersBot:
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.data = DataManager()
        self.api = MicroWorkersAPI()
        self.start_time = datetime.now()
        self.stats = {'checks': 0, 'notifications': 0}
        self.cache = set()
        self.running = True
        
    # ========== NOTIFICATION ==========
    
    def format_message(self, job):
        """Format message exactly like screenshot"""
        return f"""Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['time']}

Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['time']}

Microworkers Alerts
Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['time']}

Website: Email Submit + Click + Reply + Screenshot (Read Updated...)

${job['payment']} {job['completed']}/{job['total']} {job['remaining']} left

Open Job    {job['time']}"""
        
    async def send_to_all(self, message, keyboard=None):
        """Send message to all authorized users"""
        bot = Bot(token=self.token)
        sent = 0
        
        for uid in self.data.get_users():
            try:
                await bot.send_message(
                    chat_id=uid,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                sent += 1
                await asyncio.sleep(0.05)  # Small delay to avoid rate limits
            except Exception as e:
                logger.error(f"Failed to send to {uid}: {e}")
                
        return sent
        
    async def send_notification(self, job):
        """Send job notification"""
        cache_key = f"{job['completed']}_{job['total']}"
        
        if cache_key in self.cache:
            logger.debug("Duplicate notification skipped")
            return
            
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 OPEN JOB", url="https://www.microworkers.com/jobs.php")
        ]])
        
        sent = await self.send_to_all(self.format_message(job), keyboard)
        
        self.cache.add(cache_key)
        self.stats['notifications'] += 1
        
        logger.info(f"✅ Notification sent to {sent} users | {job['completed']}/{job['total']}")
        
        # Clear old cache
        if len(self.cache) > 100:
            self.cache.clear()
            
    # ========== MONITORING ==========
    
    async def monitor(self):
        """Monitor jobs"""
        logger.info("🔍 Monitoring started...")
        
        while self.running:
            try:
                self.stats['checks'] += 1
                
                jobs = await self.api.get_jobs()
                
                if jobs:
                    job = self.api.find_job(jobs)
                    if job:
                        await self.send_notification(job)
                else:
                    logger.debug("No jobs received")
                    
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(60)
                
    # ========== COMMANDS ==========
    
    async def start(self, update, context):
        """Start command"""
        user_id = update.effective_user.id
        
        if not self.data.is_user(user_id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        msg = f"""🚀 *MicroWorkers Bot*

📌 *Monitoring:* `Email Submit + Click + Reply + Screenshot`
⏱ *Interval:* `{CHECK_INTERVAL}s`
🌐 *Web:* [{RENDER_URL}]({RENDER_URL})

"""
        if self.data.is_owner(user_id):
            msg += """👑 *Owner Commands*
`/users` - List users
`/add [id]` - Add user
`/remove [id]` - Remove user
`/broadcast [msg]` - Broadcast

"""
            
        msg += """📱 *User Commands*
`/status` - Bot status
`/test` - Test notification
`/help` - Help"""
        
        await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
        
    async def status(self, update, context):
        """Status command"""
        user_id = update.effective_user.id
        if not self.data.is_user(user_id):
            return
            
        uptime = datetime.now() - self.start_time
        hours = uptime.total_seconds() / 3600
        
        msg = f"""📊 *Bot Status*

```

Uptime: {str(uptime).split('.')[0]}
Checks: {self.stats['checks']}
Notifications: {self.stats['notifications']}
Users: {len(self.data.get_users())}
Checks/hr: {(self.stats['checks']/max(1, hours)):.1f}

```"""
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    async def test(self, update, context):
        """Test command"""
        user_id = update.effective_user.id
        if not self.data.is_user(user_id):
            return
            
        test_job = {
            'payment': '0.10',
            'completed': 113,
            'total': 400,
            'remaining': 287,
            'time': datetime.now().strftime('%d %H:%M')
        }
        
        await self.send_notification(test_job)
        await update.message.reply_text("✅ Test notification sent!")
        
    async def help(self, update, context):
        """Help command"""
        user_id = update.effective_user.id
        if not self.data.is_user(user_id):
            return
            
        msg = f"""📚 *Help*

This bot monitors MicroWorkers for:
`Email Submit + Click + Reply + Screenshot`

*Commands:*
/start - Welcome message
/status - Bot status
/test - Test notification
/help - This help

*Web Interface:*
[{RENDER_URL}]({RENDER_URL})"""
        
        await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
        
    # ========== OWNER COMMANDS ==========
    
    async def users(self, update, context):
        """List users - Owner only"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        msg = "👥 *Authorized Users*\n\n"
        
        for uid in self.data.get_users():
            if uid == OWNER_ID:
                msg += f"👑 `{uid}` (Owner)\n"
            else:
                msg += f"👤 `{uid}`\n"
                
        msg += f"\nTotal: {len(self.data.get_users())}"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    async def add(self, update, context):
        """Add user - Owner only"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        try:
            new_id = int(context.args[0])
            if self.data.add_user(new_id):
                await update.message.reply_text(f"✅ Added user `{new_id}`")
            else:
                await update.message.reply_text(f"⚠️ User `{new_id}` already exists")
        except (IndexError, ValueError):
            await update.message.reply_text("❌ Usage: /add [user_id]")
            
    async def remove(self, update, context):
        """Remove user - Owner only"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        try:
            rem_id = int(context.args[0])
            if self.data.remove_user(rem_id):
                await update.message.reply_text(f"✅ Removed user `{rem_id}`")
            else:
                await update.message.reply_text(f"⚠️ Cannot remove owner or user not found")
        except (IndexError, ValueError):
            await update.message.reply_text("❌ Usage: /remove [user_id]")
            
    async def broadcast(self, update, context):
        """Broadcast message - Owner only"""
        user_id = update.effective_user.id
        if not self.data.is_owner(user_id):
            return
            
        if not context.args:
            await update.message.reply_text("❌ Usage: /broadcast [message]")
            return
            
        message = " ".join(context.args)
        broadcast_msg = f"📢 *Broadcast from Owner*\n\n{message}"
        
        sent = await self.send_to_all(broadcast_msg, None)
        
        await update.message.reply_text(f"✅ Broadcast sent to {sent} users")
        
    # ========== RUN ==========
    
    async def run(self):
        """Run the bot"""
        print("\n" + "="*50)
        print("🚀 MICROWORKERS BOT STARTING...")
        print("="*50)
        print(f"👑 Owner: {OWNER_ID}")
        print(f"📊 Users: {len(self.data.get_users())}")
        print(f"🌐 URL: {RENDER_URL}")
        print("="*50 + "\n")
        
        # Send startup to owner
        try:
            bot = Bot(token=self.token)
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"""✅ *Bot Started Successfully!*

👑 *Owner:* `{OWNER_ID}`
📊 *Users:* `{len(self.data.get_users())}`
⏱ *Interval:* `{CHECK_INTERVAL}s`
🌐 *Web:* [{RENDER_URL}]({RENDER_URL})

📌 Monitoring: `Email Submit + Click + Reply + Screenshot`""",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            logger.info("✅ Startup message sent to owner")
        except Exception as e:
            logger.error(f"Failed to send startup: {e}")
            
        # Create application
        app = Application.builder().token(self.token).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("test", self.test))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("users", self.users))
        app.add_handler(CommandHandler("add", self.add))
        app.add_handler(CommandHandler("remove", self.remove))
        app.add_handler(CommandHandler("broadcast", self.broadcast))
        
        # Start monitoring
        asyncio.create_task(self.monitor())
        
        # Start bot
        logger.info("✅ Bot is running!")
        await app.run_polling(drop_pending_updates=True)

# ==================== WEB SERVER ====================

async def web_server():
    """Web server for Render health checks and status"""
    app = web.Application()
    
    async def home(request):
        """Home page with Render URL"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>MicroWorkers Bot</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    margin: 0;
                    padding: 20px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    color: white;
                }}
                .card {{
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    padding: 40px;
                    max-width: 600px;
                    width: 100%;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                    border: 1px solid rgba(255,255,255,0.2);
                }}
                h1 {{ margin: 0 0 10px; font-size: 2.5em; }}
                .status {{
                    display: inline-block;
                    background: #10b981;
                    padding: 8px 20px;
                    border-radius: 50px;
                    font-weight: bold;
                    margin: 20px 0;
                }}
                .info {{
                    background: rgba(0,0,0,0.2);
                    padding: 20px;
                    border-radius: 10px;
                    margin: 20px 0;
                }}
                .info p { margin: 10px 0; }
                code {{
                    background: rgba(0,0,0,0.3);
                    padding: 3px 8px;
                    border-radius: 5px;
                    font-size: 0.9em;
                }}
                .links {{
                    display: flex;
                    gap: 20px;
                    justify-content: center;
                    margin-top: 30px;
                }}
                .links a {{
                    color: white;
                    text-decoration: none;
                    padding: 10px 20px;
                    background: rgba(255,255,255,0.2);
                    border-radius: 50px;
                    transition: 0.3s;
                }}
                .links a:hover {{
                    background: rgba(255,255,255,0.3);
                    transform: translateY(-2px);
                }}
                .footer {{
                    margin-top: 30px;
                    text-align: center;
                    opacity: 0.8;
                    font-size: 0.9em;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🚀 MicroWorkers Bot</h1>
                <div class="status">✅ ONLINE</div>
                
                <div class="info">
                    <p><strong>👑 Owner:</strong> <code>{OWNER_ID}</code></p>
                    <p><strong>📊 Status:</strong> Monitoring active</p>
                    <p><strong>📌 Job:</strong> Email Submit + Click + Reply + Screenshot</p>
                    <p><strong>⏱ Interval:</strong> {CHECK_INTERVAL}s</p>
                    <p><strong>🌐 URL:</strong> <code>{RENDER_URL}</code></p>
                </div>
                
                <div class="links">
                    <a href="/health">🔍 Health Check</a>
                    <a href="https://t.me/{(await get_bot_username())}">📱 Telegram Bot</a>
                </div>
                
                <div class="footer">
                    <p>Made with ❤️ for MicroWorkers</p>
                </div>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
        
    async def health(request):
        """Health check endpoint"""
        return web.json_response({
            'status': 'healthy',
            'owner': OWNER_ID,
            'uptime': str(datetime.now() - bot.start_time).split('.')[0],
            'checks': bot.stats['checks'],
            'notifications': bot.stats['notifications']
        })
        
    async def get_bot_username():
        """Get bot username for link"""
        try:
            bot_instance = Bot(token=TELEGRAM_TOKEN)
            me = await bot_instance.get_me()
            return me.username
        except:
            return "your_bot"
            
    app.router.add_get('/', home)
    app.router.add_get('/health', health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Web server running at {RENDER_URL}")

# ==================== GLOBAL BOT INSTANCE ====================

bot = None

# ==================== MAIN ====================

async def main():
    """Main function"""
    global bot
    bot = MicroWorkersBot()
    
    # Start web server
    await web_server()
    
    # Run bot
    await bot.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
