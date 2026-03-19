#!/usr/bin/env python3
"""
MicroWorkers ULTIMATE Bot - Telegram + Callbacks + Web Interface
All in one file - Just deploy and forget!
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
from typing import Dict, List, Optional, Any
from aiohttp import web

# Telegram imports
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError, TimedOut, NetworkError
from telegram.ext import Application, CommandHandler, ContextTypes

# Try colorama (optional)
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLORS = True
except ImportError:
    COLORS = False
    Fore = type('Fore', (), {'RED':'', 'GREEN':'', 'YELLOW':'', 'BLUE':'', 'MAGENTA':'', 'CYAN':'', 'RESET':''})()
    Style = type('Style', (), {'BRIGHT':'', 'RESET_ALL':''})()

# ==================== CONFIGURATION ====================

class Config:
    """Configuration from environment variables"""
    
    # Telegram (REQUIRED)
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    
    # API Keys (your provided keys)
    API_SECRET_KEY = os.environ.get('API_SECRET_KEY', 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f')
    VCODE_SECRET_KEY = os.environ.get('VCODE_SECRET_KEY', '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440')
    
    # API Settings
    API_BASE_URL = os.environ.get('API_BASE_URL', 'https://ttv.microworkers.com')
    API_VERSION = '2.0.0'
    
    # Job Settings
    TARGET_JOB = 'Email Submit + Click + Reply + Screenshot'
    CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '30'))
    NOTIFICATION_COOLDOWN = int(os.environ.get('NOTIFICATION_COOLDOWN', '300'))
    
    # Web Server
    PORT = int(os.environ.get('PORT', 10000))
    HOST = '0.0.0.0'
    
    # Bot Settings
    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== API CLIENT ====================

class MicroWorkersAPI:
    """API Client for MicroWorkers v2.0.0"""
    
    def __init__(self):
        self.api_key = Config.API_SECRET_KEY
        self.vcode_key = Config.VCODE_SECRET_KEY
        self.base_url = Config.API_BASE_URL
        self.session = None
        self.request_count = 0
        self.last_jobs = []
        
    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': f'MicroWorkersBot/{Config.API_VERSION}',
                    'Accept': 'application/json',
                },
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None
            
    def _generate_signatures(self, timestamp: str, method: str, path: str) -> Dict:
        """Generate API signatures"""
        payload = f"{timestamp}{method}{path}"
        
        vcode = hmac.new(
            self.vcode_key.encode(), 
            payload.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        auth = hmac.new(
            self.api_key.encode(), 
            payload.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        return {
            'X-API-Key': self.api_key,
            'X-VCode': vcode,
            'X-Auth': auth,
            'X-Timestamp': timestamp
        }
        
    async def get_jobs(self) -> Optional[List[Dict]]:
        """Fetch jobs from API"""
        try:
            await self.ensure_session()
            
            timestamp = str(int(time.time() * 1000))
            path = "/api/v2/jobs?type=all&limit=200"
            
            headers = self._generate_signatures(timestamp, 'GET', path)
            headers['Content-Type'] = 'application/json'
            
            async with self.session.get(
                f"{self.base_url}{path}", 
                headers=headers
            ) as response:
                
                self.request_count += 1
                
                if response.status == 200:
                    data = await response.json()
                    jobs = data.get('jobs') if isinstance(data, dict) else data
                    self.last_jobs = jobs or []
                    logger.info(f"📊 API Call #{self.request_count} | Jobs: {len(self.last_jobs)}")
                    return self.last_jobs
                else:
                    error = await response.text()
                    logger.error(f"❌ API Error {response.status}: {error[:100]}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ API Error: {e}")
            return None
            
    def find_target_job(self) -> Optional[Dict]:
        """Find our target job"""
        if not self.last_jobs:
            return None
            
        keywords = ['email', 'submit', 'click', 'reply', 'screenshot']
        
        for job in self.last_jobs:
            try:
                title = str(job.get('title', job.get('name', ''))).lower()
                
                if all(k in title for k in keywords):
                    completed = int(job.get('completed_count', job.get('completed', 0)))
                    total = int(job.get('total_jobs', job.get('total', 100)))
                    remaining = max(0, total - completed)
                    
                    return {
                        'payment': '0.10',
                        'completed': completed,
                        'total': total,
                        'remaining': remaining,
                        'timestamp': datetime.now().strftime('%d %H:%M'),
                        'campaign_id': job.get('id'),
                        'success_rate': job.get('success_rate', 'N/A'),
                        'ttr': job.get('time_to_rate', job.get('ttr', 'N/A'))
                    }
            except:
                continue
                
        return None

# ==================== WEB SERVER & CALLBACK HANDLER ====================

class WebServer:
    """Web server for callbacks and status page"""
    
    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.runner = None
        self.callback_logs = []
        self.setup_routes()
        
    def setup_routes(self):
        """Setup all routes"""
        self.app.router.add_get('/', self.home_page)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/logs', self.view_logs)
        self.app.router.add_get('/stats', self.view_stats)
        
        # Callback endpoints
        self.app.router.add_get('/callback/campaign', self.campaign_callback)
        self.app.router.add_get('/callback/task', self.task_callback)
        self.app.router.add_post('/callback/campaign', self.campaign_callback)
        self.app.router.add_post('/callback/task', self.task_callback)
        
    async def home_page(self, request):
        """Beautiful home page"""
        uptime = datetime.now() - self.bot.start_time
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>MicroWorkers Premium Bot</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                    color: white;
                }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .header {{
                    text-align: center;
                    padding: 40px 0;
                }}
                .header h1 {{
                    font-size: 3em;
                    margin-bottom: 10px;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                }}
                .status-card {{
                    background: rgba(255,255,255,0.1);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    padding: 30px;
                    margin: 20px 0;
                    border: 1px solid rgba(255,255,255,0.2);
                }}
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }}
                .card {{
                    background: rgba(255,255,255,0.1);
                    backdrop-filter: blur(10px);
                    border-radius: 15px;
                    padding: 25px;
                    border: 1px solid rgba(255,255,255,0.2);
                    transition: transform 0.3s;
                }}
                .card:hover {{ transform: translateY(-5px); }}
                .card h3 {{
                    margin-bottom: 15px;
                    border-bottom: 2px solid rgba(255,255,255,0.2);
                    padding-bottom: 10px;
                }}
                .stat-value {{
                    font-size: 2em;
                    font-weight: bold;
                    margin: 10px 0;
                }}
                .badge {{
                    display: inline-block;
                    padding: 5px 15px;
                    border-radius: 50px;
                    font-size: 0.9em;
                    font-weight: bold;
                }}
                .badge.online {{ background: #10b981; }}
                .badge.offline {{ background: #ef4444; }}
                .callback-url {{
                    background: rgba(0,0,0,0.3);
                    padding: 15px;
                    border-radius: 10px;
                    margin: 10px 0;
                    font-family: monospace;
                }}
                .logs {{
                    background: rgba(0,0,0,0.3);
                    border-radius: 10px;
                    padding: 15px;
                    max-height: 300px;
                    overflow-y: auto;
                    font-family: monospace;
                    font-size: 0.9em;
                }}
                .log-entry {{
                    padding: 5px;
                    border-bottom: 1px solid rgba(255,255,255,0.1);
                }}
                .footer {{
                    text-align: center;
                    margin-top: 40px;
                    padding: 20px;
                    color: rgba(255,255,255,0.7);
                }}
                @media (max-width: 768px) {{
                    .header h1 {{ font-size: 2em; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚀 MicroWorkers Premium Bot</h1>
                    <p>Real-time job monitoring & notifications</p>
                </div>
                
                <div class="status-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h2>🤖 Bot Status</h2>
                        <span class="badge online">🟢 ONLINE</span>
                    </div>
                    <div style="margin-top: 20px;">
                        <p><strong>📌 Monitoring:</strong> {Config.TARGET_JOB}</p>
                        <p><strong>⏱ Check Interval:</strong> {Config.CHECK_INTERVAL} seconds</p>
                        <p><strong>📡 API Version:</strong> {Config.API_VERSION}</p>
                        <p><strong>🕒 Uptime:</strong> {str(uptime).split('.')[0]}</p>
                    </div>
                </div>
                
                <div class="grid">
                    <div class="card">
                        <h3>📊 Statistics</h3>
                        <div class="stat-value">{self.bot.stats['checks']}</div>
                        <p>Total API Checks</p>
                        <div class="stat-value">{self.bot.stats['notifications']}</div>
                        <p>Notifications Sent</p>
                        <div class="stat-value">{self.bot.stats['callbacks']}</div>
                        <p>Callbacks Received</p>
                    </div>
                    
                    <div class="card">
                        <h3>🔗 Callback URLs</h3>
                        <div class="callback-url">
                            <strong>Campaign:</strong><br>
                            <code>https://{request.host}/callback/campaign</code>
                        </div>
                        <div class="callback-url">
                            <strong>Task:</strong><br>
                            <code>https://{request.host}/callback/task</code>
                        </div>
                        <div class="callback-url">
                            <strong>Health Check:</strong><br>
                            <code>https://{request.host}/health</code>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h3>📋 Recent Callbacks</h3>
                    <div class="logs" id="logs">
                        {self.format_logs()}
                    </div>
                    <div style="margin-top: 10px;">
                        <a href="/logs" style="color: white;">View All Logs →</a>
                    </div>
                </div>
                
                <div class="card">
                    <h3>💬 Telegram Commands</h3>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;">
                        <div><code>/start</code> - Welcome</div>
                        <div><code>/status</code> - Bot status</div>
                        <div><code>/stats</code> - Statistics</div>
                        <div><code>/test</code> - Test notification</div>
                        <div><code>/help</code> - Show help</div>
                    </div>
                </div>
                
                <div class="footer">
                    <p>Made with ❤️ for MicroWorkers | API v{Config.API_VERSION}</p>
                </div>
            </div>
            
            <script>
                // Auto-refresh logs every 10 seconds
                setTimeout(() => location.reload(), 10000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
        
    def format_logs(self):
        """Format logs for display"""
        if not self.callback_logs:
            return "<div class='log-entry'>No callbacks yet</div>"
            
        logs = ""
        for log in self.callback_logs[-10:]:  # Last 10
            logs += f"<div class='log-entry'>📌 {log}</div>"
        return logs
        
    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'uptime': str(datetime.now() - self.bot.start_time)
        })
        
    async def view_logs(self, request):
        """View all logs"""
        return web.json_response({
            'logs': self.callback_logs[-50:]  # Last 50 logs
        })
        
    async def view_stats(self, request):
        """View statistics"""
        return web.json_response({
            'bot': self.bot.stats,
            'uptime': str(datetime.now() - self.bot.start_time),
            'config': {
                'interval': Config.CHECK_INTERVAL,
                'target': Config.TARGET_JOB,
                'api_version': Config.API_VERSION
            }
        })
        
    async def campaign_callback(self, request):
        """Handle campaign finished notifications"""
        params = dict(request.query)
        log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] Campaign Finished: {params}"
        
        # Log it
        self.callback_logs.append(log_entry)
        self.bot.stats['callbacks'] += 1
        
        # Save to file
        try:
            with open('callbacks.log', 'a') as f:
                f.write(json.dumps({
                    'time': datetime.now().isoformat(),
                    'type': 'campaign',
                    'data': params
                }) + '\n')
        except:
            pass
            
        # Send Telegram notification
        try:
            msg = (
                f"🎯 *Campaign Finished*\n\n"
                f"```\n"
                f"ID: {params.get('mw_campaign_id', 'N/A')}\n"
                f"Type: {params.get('mw_campaign_type', 'N/A')}\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                f"```"
            )
            await self.bot.bot.send_message(
                chat_id=Config.TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode='Markdown'
            )
        except:
            pass
            
        return web.Response(text="OK")
        
    async def task_callback(self, request):
        """Handle task submitted notifications"""
        params = dict(request.query)
        log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] Task Submitted: {params}"
        
        # Log it
        self.callback_logs.append(log_entry)
        self.bot.stats['callbacks'] += 1
        
        # Save to file
        try:
            with open('callbacks.log', 'a') as f:
                f.write(json.dumps({
                    'time': datetime.now().isoformat(),
                    'type': 'task',
                    'data': params
                }) + '\n')
        except:
            pass
            
        return web.Response(text="OK")
        
    async def start(self):
        """Start web server"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, Config.HOST, Config.PORT)
        await site.start()
        logger.info(f"🌐 Web server running on http://{Config.HOST}:{Config.PORT}")
        
    async def stop(self):
        """Stop web server"""
        if self.runner:
            await self.runner.cleanup()

# ==================== TELEGRAM BOT ====================

class MicroWorkersBot:
    """Main Telegram Bot"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.bot = Bot(token=self.token)
        self.api = MicroWorkersAPI()
        self.web = WebServer(self)
        self.application = None
        self.running = True
        self.start_time = datetime.now()
        self.notification_cache = {}
        
        self.stats = {
            'checks': 0,
            'notifications': 0,
            'callbacks': 0,
            'errors': 0
        }
        
    async def verify_telegram(self) -> bool:
        """Verify Telegram connection"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text="🟢 *Bot Started Successfully!*\n\n"
                     f"Monitoring: `{Config.TARGET_JOB}`\n"
                     f"Interval: `{Config.CHECK_INTERVAL}s`\n\n"
                     f"🌐 Web Interface: https://tg-bot-hmpa.onrender.com",
                parse_mode='Markdown'
            )
            logger.info("✅ Telegram verified")
            return True
        except TelegramError as e:
            logger.error(f"❌ Telegram error: {e}")
            return False
            
    async def start(self):
        """Start the bot"""
        print("\n" + "="*60)
        print("🚀 MicroWorkers ULTIMATE Bot Starting...")
        print("="*60 + "\n")
        
        # Check config
        if not self.token or not self.chat_id:
            logger.error("❌ Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
            return
            
        # Verify Telegram
        if not await self.verify_telegram():
            logger.error("❌ Failed to connect to Telegram")
            return
            
        # Start web server
        await self.web.start()
        
        # Setup Telegram application
        self.application = Application.builder().token(self.token).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("stats", self.cmd_stats))
        self.application.add_handler(CommandHandler("test", self.cmd_test))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        
        # Start monitoring
        asyncio.create_task(self.monitor_jobs())
        
        # Start bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("✅ Bot fully operational!")
        
        # Keep running
        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await self.shutdown()
            
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 Shutting down...")
        self.running = False
        
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            
        await self.web.stop()
        await self.api.close()
        
    async def monitor_jobs(self):
        """Monitor jobs continuously"""
        logger.info("🔍 Starting job monitoring...")
        
        while self.running:
            try:
                self.stats['checks'] += 1
                
                # Fetch jobs
                jobs = await self.api.get_jobs()
                
                if jobs:
                    # Find target job
                    job = self.api.find_target_job()
                    
                    if job:
                        await self.send_notification(job)
                        
                await asyncio.sleep(Config.CHECK_INTERVAL)
                
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"❌ Monitor error: {e}")
                await asyncio.sleep(60)
                
    async def send_notification(self, job: Dict):
        """Send job notification"""
        try:
            # Check cache
            cache_key = f"{job['completed']}_{job['total']}"
            if cache_key in self.notification_cache:
                age = (datetime.now() - self.notification_cache[cache_key]).seconds
                if age < Config.NOTIFICATION_COOLDOWN:
                    return
                    
            # Format message exactly like screenshot
            message = f"""Reply + Screenshot (Read Updated...)

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
            
            # Create button
            keyboard = [[
                InlineKeyboardButton(
                    "🚀 OPEN JOB",
                    url="https://www.microworkers.com/jobs.php"
                )
            ]]
            
            # Send
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Update cache and stats
            self.notification_cache[cache_key] = datetime.now()
            self.stats['notifications'] += 1
            
            logger.info(f"✅ Notification #{self.stats['notifications']} sent | {job['completed']}/{job['total']}")
            
            # Clean cache
            self.clean_cache()
            
        except Exception as e:
            logger.error(f"❌ Send error: {e}")
            
    def clean_cache(self):
        """Clean old cache entries"""
        now = datetime.now()
        expired = [k for k, v in self.notification_cache.items() 
                  if (now - v).seconds > 3600]
        for k in expired:
            del self.notification_cache[k]
            
    # ========== COMMAND HANDLERS ==========
    
    async def cmd_start(self, update, context):
        await update.message.reply_text(
            f"🚀 *MicroWorkers Ultimate Bot*\n\n"
            f"📌 *Monitoring:* `{Config.TARGET_JOB}`\n"
            f"⏱ *Interval:* `{Config.CHECK_INTERVAL}s`\n"
            f"🌐 *Web:* `https://tg-bot-hmpa.onrender.com`\n\n"
            f"*Commands:*\n"
            f"/status - Current status\n"
            f"/stats - Statistics\n"
            f"/test - Test notification\n"
            f"/help - Help",
            parse_mode='Markdown'
        )
        
    async def cmd_status(self, update, context):
        uptime = datetime.now() - self.start_time
        await update.message.reply_text(
            f"📊 *Bot Status*\n\n"
            f"```\n"
            f"Uptime: {str(uptime).split('.')[0]}\n"
            f"Checks: {self.stats['checks']}\n"
            f"Notifications: {self.stats['notifications']}\n"
            f"Callbacks: {self.stats['callbacks']}\n"
            f"Errors: {self.stats['errors']}\n"
            f"```\n"
            f"🌐 {Config.TARGET_JOB}",
            parse_mode='Markdown'
        )
        
    async def cmd_stats(self, update, context):
        await update.message.reply_text(
            f"📈 *Detailed Statistics*\n\n"
            f"*Performance*\n"
            f"├ Checks: {self.stats['checks']}\n"
            f"├ Notifications: {self.stats['notifications']}\n"
            f"├ Callbacks: {self.stats['callbacks']}\n"
            f"└ Errors: {self.stats['errors']}\n\n"
            f"*Settings*\n"
            f"├ Interval: {Config.CHECK_INTERVAL}s\n"
            f"├ Cooldown: {Config.NOTIFICATION_COOLDOWN}s\n"
            f"└ API: v{Config.API_VERSION}",
            parse_mode='Markdown'
        )
        
    async def cmd_test(self, update, context):
        test_job = {
            'payment': '0.10',
            'completed': 113,
            'total': 400,
            'remaining': 287,
            'timestamp': datetime.now().strftime('%d %H:%M')
        }
        await self.send_notification(test_job)
        await update.message.reply_text("✅ Test notification sent!")
        
    async def cmd_help(self, update, context):
        await update.message.reply_text(
            f"📚 *Help*\n\n"
            f"*Commands*\n"
            f"/start - Welcome\n"
            f"/status - Bot status\n"
            f"/stats - Statistics\n"
            f"/test - Test notification\n"
            f"/help - This help\n\n"
            f"*Web Interface*\n"
            f"https://tg-bot-hmpa.onrender.com",
            parse_mode='Markdown'
        )

# ==================== MAIN ====================

async def main():
    """Main entry point"""
    bot = MicroWorkersBot()
    await bot.start()

def run():
    """Run the bot"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    run()
