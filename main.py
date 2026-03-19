#!/usr/bin/env python3
"""
MicroWorkers Premium Job Bot - API v2.0.0
Complete solution for "Email Submit + Click + Reply + Screenshot" job notifications
"""

import os
import sys
import json
import asyncio
import aiohttp
import hmac
import hashlib
import time
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from logging.handlers import RotatingFileHandler
import traceback

# Optional imports with fallback
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    COLORS_AVAILABLE = False
    # Create dummy color classes
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ''
    class Style:
        BRIGHT = RESET_ALL = ''

try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.error import TelegramError, TimedOut, NetworkError
    from telegram.ext import Application, CommandHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError as e:
    print(f"❌ Telegram import error: {e}")
    print("📦 Run: pip install python-telegram-bot==20.7")
    TELEGRAM_AVAILABLE = False
    sys.exit(1)

# ==================== CONFIGURATION ====================

class Config:
    """Configuration management from environment variables"""
    
    # Required
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    
    # API Keys (your provided keys)
    API_SECRET_KEY = os.environ.get('API_SECRET_KEY', 'f0737b7d3a2c4de47564a47ee55a59ea4f16947831848c86efafa0be926d003f')
    VCODE_SECRET_KEY = os.environ.get('VCODE_SECRET_KEY', '121b0fb13a9745890bf300f622e104ce39f5bc42ea8ec8915fd2bda02618d440')
    
    # API Endpoints (v2.0.0)
    API_BASE_URL = os.environ.get('API_BASE_URL', 'https://ttv.microworkers.com')
    API_VERSION = '2.0.0'
    
    # Job Settings
    TARGET_JOB_PATTERN = os.environ.get('TARGET_JOB_PATTERN', 'Email Submit + Click + Reply + Screenshot')
    CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '30'))  # seconds
    NOTIFICATION_COOLDOWN = int(os.environ.get('NOTIFICATION_COOLDOWN', '300'))  # 5 minutes
    
    # Bot Settings
    DEBUG_MODE = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    MAX_NOTIFICATION_CACHE = int(os.environ.get('MAX_NOTIFICATION_CACHE', '100'))
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        if not cls.TELEGRAM_TOKEN:
            errors.append("❌ TELEGRAM_TOKEN is required")
        if not cls.TELEGRAM_CHAT_ID:
            errors.append("❌ TELEGRAM_CHAT_ID is required")
        if not cls.API_SECRET_KEY:
            errors.append("❌ API_SECRET_KEY is required")
        if not cls.VCODE_SECRET_KEY:
            errors.append("❌ VCODE_SECRET_KEY is required")
            
        return errors

# ==================== LOGGING SETUP ====================

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors"""
    
    format_str = "%(asctime)s | %(levelname)-8s | %(message)s"
    
    COLOR_CODES = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT
    }
    
    def format(self, record):
        # Add colors if available
        if COLORS_AVAILABLE:
            color = self.COLOR_CODES.get(record.levelno, Fore.WHITE)
            record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
            
        # Format message
        formatter = logging.Formatter(
            self.format_str,
            datefmt='%H:%M:%S'
        )
        return formatter.format(record)

def setup_logging():
    """Setup logging with file and console handlers"""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler with colors
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ColoredFormatter())
    logger.addHandler(console)
    
    # File handler for errors
    try:
        file_handler = RotatingFileHandler(
            'bot_errors.log',
            maxBytes=1024*1024,  # 1MB
            backupCount=3
        )
        file_handler.setLevel(logging.ERROR)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)
    except:
        pass  # File logging optional
    
    return logger

logger = setup_logging()

# ==================== API CLIENT (v2.0.0) ====================

class MicroWorkersAPIClient:
    """API Client for MicroWorkers v2.0.0"""
    
    def __init__(self):
        self.api_key = Config.API_SECRET_KEY
        self.vcode_key = Config.VCODE_SECRET_KEY
        self.base_url = Config.API_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_count = 0
        self.last_request_time = 0
        self.rate_limit_remaining = 100
        self.rate_limit_reset = 0
        
    async def __aenter__(self):
        await self.ensure_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def ensure_session(self):
        """Ensure aiohttp session exists"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': f'MicroWorkersBot/{Config.API_VERSION}',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
    async def close(self):
        """Close session properly"""
        if self.session:
            await self.session.close()
            self.session = None
            
    def _generate_signatures(self, timestamp: str, method: str, path: str) -> Dict[str, str]:
        """
        Generate authentication signatures as per API v2.0.0
        
        The API requires:
        - X-VCode: HMAC-SHA256 of (timestamp + method + path) using vcode_secret_key
        - X-Auth: HMAC-SHA256 of (timestamp + method + path) using api_secret_key
        """
        try:
            # Create payload
            payload = f"{timestamp}{method}{path}"
            
            # Generate VCode signature
            vcode_signature = hmac.new(
                self.vcode_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Generate Auth signature
            auth_signature = hmac.new(
                self.api_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            logger.debug(f"🔐 Signatures generated - Timestamp: {timestamp}")
            
            return {
                'X-VCode': vcode_signature,
                'X-Auth': auth_signature,
                'X-Timestamp': timestamp,
                'X-API-Key': self.api_key
            }
            
        except Exception as e:
            logger.error(f"❌ Signature generation failed: {e}")
            raise
            
    async def get_jobs(self, job_type: str = 'all', limit: int = 200) -> Optional[List[Dict]]:
        """
        Fetch jobs from API v2.0.0
        
        Endpoint: GET /api/v2/jobs?type={type}&limit={limit}
        """
        try:
            await self.ensure_session()
            
            # Rate limiting
            current_time = time.time()
            if current_time - self.last_request_time < 1.0:
                await asyncio.sleep(1.0)
                
            # Prepare request
            timestamp = str(int(time.time() * 1000))
            path = f"/api/v2/jobs?type={job_type}&limit={limit}"
            method = "GET"
            
            # Generate signatures
            headers = self._generate_signatures(timestamp, method, path)
            
            # Make request
            url = f"{self.base_url}{path}"
            logger.debug(f"🌐 Requesting: {url}")
            
            async with self.session.get(url, headers=headers) as response:
                self.last_request_time = time.time()
                self.request_count += 1
                
                # Track rate limits
                self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 100))
                self.rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
                
                # Handle response
                if response.status == 200:
                    data = await response.json()
                    jobs = data.get('jobs') if isinstance(data, dict) else data
                    
                    logger.info(
                        f"{Fore.GREEN}📊 API Call #{self.request_count} | "
                        f"Status: {response.status} | "
                        f"Jobs: {len(jobs) if jobs else 0} | "
                        f"Rate: {self.rate_limit_remaining}{Style.RESET_ALL}"
                    )
                    
                    return jobs
                    
                elif response.status == 401:
                    logger.error(f"{Fore.RED}❌ Authentication failed - Check API keys{Style.RESET_ALL}")
                    return None
                    
                elif response.status == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"⏳ Rate limited. Waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    return None
                    
                else:
                    error_text = await response.text()
                    logger.error(f"❌ API Error {response.status}: {error_text[:200]}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("⏰ Request timeout")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"🌐 Network error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            logger.debug(traceback.format_exc())
            return None
            
    def find_target_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """
        Find jobs matching target pattern
        Uses fuzzy matching to handle variations in job titles
        """
        matches = []
        
        if not jobs:
            return matches
            
        # Keywords to match (all must be present)
        keywords = ['email', 'submit', 'click', 'reply', 'screenshot']
        
        for job in jobs:
            try:
                # Get job title from various possible fields
                title = str(job.get('title', job.get('name', job.get('description', '')))).lower()
                
                # Check if all keywords present
                if all(keyword in title for keyword in keywords):
                    
                    # Extract job data with safe conversion
                    completed = self._safe_int(job.get('completed_count', job.get('completed', 0)))
                    total = self._safe_int(job.get('total_jobs', job.get('total', 100)))
                    remaining = max(0, total - completed)
                    
                    job_info = {
                        'id': job.get('id', 'unknown'),
                        'name': 'Email Submit + Click + Reply + Screenshot',
                        'payment': '0.10',
                        'completed': completed,
                        'total': total,
                        'remaining': remaining,
                        'timestamp': datetime.now().strftime('%d %H:%M'),
                        'success_rate': job.get('success_rate', 'N/A'),
                        'ttr': job.get('time_to_rate', job.get('ttr', 'N/A')),
                        'country_restrictions': job.get('country_restrictions', []),
                        'requirements': job.get('requirements', {})
                    }
                    
                    matches.append(job_info)
                    
                    logger.debug(f"🎯 Match found: {completed}/{total} completed")
                    
            except Exception as e:
                logger.error(f"Error parsing job: {e}")
                continue
                
        return matches
        
    def _safe_int(self, value: Any, default: int = 0) -> int:
        """Safely convert value to int"""
        try:
            return int(float(value)) if value not in (None, 'N/A') else default
        except (ValueError, TypeError):
            return default

# ==================== TELEGRAM BOT ====================

class MicroWorkersBot:
    """Premium Telegram Bot for job notifications"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.api = MicroWorkersAPIClient()
        self.bot = Bot(token=self.token)
        self.application = None
        
        # State tracking
        self.notification_cache = {}
        self.stats = {
            'start_time': datetime.now(),
            'total_checks': 0,
            'total_notifications': 0,
            'total_api_calls': 0,
            'errors': 0,
            'last_check_time': None,
            'last_notification_time': None
        }
        
        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"{Fore.YELLOW}🛑 Shutdown signal received{Style.RESET_ALL}")
        sys.exit(0)
        
    async def start(self):
        """Start the bot"""
        try:
            # Print banner
            self.print_banner()
            
            # Validate config
            errors = Config.validate()
            if errors:
                for error in errors:
                    logger.error(error)
                return
                
            # Setup application
            self.application = Application.builder().token(self.token).build()
            
            # Add command handlers
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("stats", self.cmd_stats))
            self.application.add_handler(CommandHandler("test", self.cmd_test))
            self.application.add_handler(CommandHandler("help", self.cmd_help))
            
            # Send startup message
            await self.send_startup_message()
            
            # Start monitoring in background
            asyncio.create_task(self.monitoring_loop())
            
            # Start bot
            logger.info(f"{Fore.GREEN}🚀 Bot is running...{Style.RESET_ALL}")
            await self.application.run_polling(drop_pending_updates=True)
            
        except Exception as e:
            logger.error(f"❌ Failed to start: {e}")
            logger.debug(traceback.format_exc())
            
    def print_banner(self):
        """Print startup banner"""
        banner = f"""
{Fore.CYAN}╔{'═'*50}╗
{Fore.YELLOW}║  ███╗   ███╗██╗ ██████╗██████╗  ██████╗ ██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗███████╗██████╗ ███████╗
{Fore.YELLOW}║  ████╗ ████║██║██╔════╝██╔══██╗██╔═══██╗██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗██╔════╝
{Fore.YELLOW}║  ██╔████╔██║██║██║     ██████╔╝██║   ██║██║ █╗ ██║██║   ██║██████╔╝█████╔╝ █████╗  ██████╔╝███████╗
{Fore.YELLOW}║  ██║╚██╔╝██║██║██║     ██╔══██╗██║   ██║██║███╗██║██║   ██║██╔══██╗██╔═██╗ ██╔══╝  ██╔══██╗╚════██║
{Fore.YELLOW}║  ██║ ╚═╝ ██║██║╚██████╗██║  ██║╚██████╔╝╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗███████╗██║  ██║███████║
{Fore.YELLOW}║  ╚═╝     ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝  ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝
{Fore.CYAN}╚{'═'*50}╝
{Fore.MAGENTA}⚡ Premium Job Notification Bot v{Config.API_VERSION} ⚡{Style.RESET_ALL}
{Fore.CYAN}{'─'*52}{Style.RESET_ALL}
"""
        print(banner)
        
    async def send_startup_message(self):
        """Send startup notification"""
        try:
            message = (
                f"🚀 *MicroWorkers Premium Bot Started*\n\n"
                f"```\n"
                f"📌 Monitoring: {Config.TARGET_JOB_PATTERN}\n"
                f"⏱ Check Interval: {Config.CHECK_INTERVAL}s\n"
                f"📡 API Version: {Config.API_VERSION}\n"
                f"🕒 Started: {self.stats['start_time'].strftime('%H:%M:%S')}\n"
                f"```\n\n"
                f"✨ *Features:*\n"
                f"• Real-time job alerts\n"
                f"• Smart duplicate prevention\n"
                f"• Premium formatting\n"
                f"• One-click access\n\n"
                f"📊 *Status:* `ONLINE`"
            )
            
            keyboard = [[
                InlineKeyboardButton("📊 Check Status", callback_data="status"),
                InlineKeyboardButton("📈 View Stats", callback_data="stats")
            ]]
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info("✅ Startup message sent")
            
        except Exception as e:
            logger.error(f"❌ Failed to send startup message: {e}")
            
    async def monitoring_loop(self):
        """Main monitoring loop"""
        logger.info(f"{Fore.CYAN}🔍 Starting monitoring loop...{Style.RESET_ALL}")
        
        while True:
            try:
                self.stats['total_checks'] += 1
                self.stats['last_check_time'] = datetime.now()
                
                # Fetch jobs
                jobs = await self.api.get_jobs()
                
                if jobs:
                    # Find target jobs
                    target_jobs = self.api.find_target_jobs(jobs)
                    
                    # Send notifications
                    for job in target_jobs:
                        await self.send_notification(job)
                        
                # Update stats
                self.stats['total_api_calls'] = self.api.request_count
                
                # Log status periodically
                if self.stats['total_checks'] % 10 == 0:
                    await self.log_status()
                    
                # Wait for next check
                await asyncio.sleep(Config.CHECK_INTERVAL)
                
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"❌ Monitoring error: {e}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(60)  # Wait 1 minute on error
                
    async def send_notification(self, job: Dict):
        """Send job notification"""
        try:
            # Create cache key
            cache_key = f"{job['completed']}_{job['total']}"
            
            # Check cache
            last_sent = self.notification_cache.get(cache_key)
            if last_sent:
                time_diff = (datetime.now() - last_sent).seconds
                if time_diff < Config.NOTIFICATION_COOLDOWN:
                    logger.debug(f"⏳ Cooldown: {Config.NOTIFICATION_COOLDOWN - time_diff}s remaining")
                    return
                    
            # Create message (exact screenshot format)
            message = self.format_screenshot_message(job)
            
            # Create button
            keyboard = [[
                InlineKeyboardButton(
                    "🚀 OPEN JOB",
                    url="https://www.microworkers.com/jobs.php"
                )
            ]]
            
            # Send message
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )
            
            # Update tracking
            self.notification_cache[cache_key] = datetime.now()
            self.stats['total_notifications'] += 1
            self.stats['last_notification_time'] = datetime.now()
            
            # Clean cache
            self.clean_cache()
            
            logger.info(
                f"{Fore.GREEN}✅ Notification #{self.stats['total_notifications']} | "
                f"{job['completed']}/{job['total']} ({job['remaining']} left){Style.RESET_ALL}"
            )
            
        except TimedOut:
            logger.error("⏰ Telegram timeout")
        except NetworkError as e:
            logger.error(f"🌐 Network error: {e}")
        except Exception as e:
            logger.error(f"❌ Send error: {e}")
            
    def format_screenshot_message(self, job: Dict) -> str:
        """Format message exactly like screenshot"""
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
        
    def clean_cache(self):
        """Clean old cache entries"""
        current_time = datetime.now()
        keys_to_delete = []
        
        for key, timestamp in self.notification_cache.items():
            if (current_time - timestamp).seconds > 3600:  # 1 hour
                keys_to_delete.append(key)
                
        for key in keys_to_delete:
            del self.notification_cache[key]
            
        # Limit cache size
        if len(self.notification_cache) > Config.MAX_NOTIFICATION_CACHE:
            oldest = min(self.notification_cache.items(), key=lambda x: x[1])
            del self.notification_cache[oldest[0]]
            
    async def log_status(self):
        """Log periodic status"""
        uptime = datetime.now() - self.stats['start_time']
        hours = uptime.total_seconds() / 3600
        
        logger.info(
            f"{Fore.CYAN}📊 Status | "
            f"Uptime: {hours:.1f}h | "
            f"Checks: {self.stats['total_checks']} | "
            f"Notifs: {self.stats['total_notifications']} | "
            f"API: {self.stats['total_api_calls']} | "
            f"Errors: {self.stats['errors']}{Style.RESET_ALL}"
        )
        
    # ========== COMMAND HANDLERS ==========
    
    async def cmd_start(self, update, context):
        """Handle /start command"""
        await update.message.reply_text(
            f"🚀 *MicroWorkers Premium Bot*\n\n"
            f"Monitoring: `{Config.TARGET_JOB_PATTERN}`\n\n"
            f"*Commands:*\n"
            f"/status - Check bot status\n"
            f"/stats - View statistics\n"
            f"/test - Send test notification\n"
            f"/help - Show help",
            parse_mode='Markdown'
        )
        
    async def cmd_status(self, update, context):
        """Handle /status command"""
        uptime = datetime.now() - self.stats['start_time']
        
        status = (
            f"📊 *Bot Status*\n\n"
            f"```\n"
            f"🕒 Uptime: {str(uptime).split('.')[0]}\n"
            f"🔄 Checks: {self.stats['total_checks']}\n"
            f"📨 Notifications: {self.stats['total_notifications']}\n"
            f"📡 API Calls: {self.stats['total_api_calls']}\n"
            f"⚠️ Errors: {self.stats['errors']}\n"
            f"```\n"
            f"⏱ *Next check:* Every {Config.CHECK_INTERVAL}s"
        )
        
        await update.message.reply_text(status, parse_mode='Markdown')
        
    async def cmd_stats(self, update, context):
        """Handle /stats command"""
        uptime = datetime.now() - self.stats['start_time']
        
        # Calculate rates
        checks_per_hour = self.stats['total_checks'] / (uptime.total_seconds() / 3600)
        
        stats = (
            f"📈 *Detailed Statistics*\n\n"
            f"*Time:*\n"
            f"├ Started: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"├ Uptime: {str(uptime).split('.')[0]}\n"
            f"└ Last check: {self.stats['last_check_time'].strftime('%H:%M:%S') if self.stats['last_check_time'] else 'Never'}\n\n"
            f"*Performance:*\n"
            f"├ Checks: {self.stats['total_checks']}\n"
            f"├ Notifications: {self.stats['total_notifications']}\n"
            f"├ API Calls: {self.stats['total_api_calls']}\n"
            f"└ Errors: {self.stats['errors']}\n\n"
            f"*Rates:*\n"
            f"├ Checks/hour: {checks_per_hour:.1f}\n"
            f"└ Success rate: {((self.stats['total_checks'] - self.stats['errors'])/max(1, self.stats['total_checks'])*100):.1f}%"
        )
        
        await update.message.reply_text(stats, parse_mode='Markdown')
        
    async def cmd_test(self, update, context):
        """Handle /test command - send test notification"""
        test_job = {
            'name': 'Email Submit + Click + Reply + Screenshot',
            'payment': '0.10',
            'completed': 113,
            'total': 400,
            'remaining': 287,
            'timestamp': datetime.now().strftime('%d %H:%M'),
            'success_rate': 100,
            'ttr': 7
        }
        
        await self.send_notification(test_job)
        await update.message.reply_text("✅ Test notification sent!")
        
    async def cmd_help(self, update, context):
        """Handle /help command"""
        help_text = (
            f"📚 *Help & Commands*\n\n"
            f"*Bot Info:*\n"
            f"├ Monitoring: `{Config.TARGET_JOB_PATTERN}`\n"
            f"├ Interval: {Config.CHECK_INTERVAL}s\n"
            f"└ Cooldown: {Config.NOTIFICATION_COOLDOWN}s\n\n"
            f"*Commands:*\n"
            f"├ /start - Welcome message\n"
            f"├ /status - Current status\n"
            f"├ /stats - Statistics\n"
            f"├ /test - Test notification\n"
            f"└ /help - This help\n\n"
            f"*Need help?*\n"
            f"Check logs or contact @BotFather"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')

# ==================== MAIN ====================

async def main():
    """Main entry point"""
    bot = MicroWorkersBot()
    await bot.start()

def run():
    """Run the bot with proper error handling"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(f"{Fore.YELLOW}👋 Bot stopped by user{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"{Fore.RED}💥 Fatal error: {e}{Style.RESET_ALL}")
        logger.debug(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    run()
