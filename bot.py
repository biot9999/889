"""
Telegram 私信机器人 - 完整集成版本
一个功能强大的 Telegram 机器人管理系统，用于管理多个 Telegram 账户并执行批量私信任务

功能特性：
- 多账户管理（session、tdata格式支持）
- 富媒体消息支持
- 消息个性化（变量替换）
- 智能防封策略
- 实时进度监控
- 内联按钮交互界面
"""

# ============================================================================
# 导入依赖
# ============================================================================
import asyncio
import os
import logging
import re
import enum
import shutil
import zipfile
import json
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Telegram Bot API
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# Telethon for account management
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError,
    PhoneNumberInvalidError, FloodWaitError,
    UserPrivacyRestrictedError, UserIsBlockedError,
    ChatWriteForbiddenError, UserNotMutualContactError, PeerFloodError
)

# Database
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, 
    ForeignKey, Enum as SQLEnum, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

# ============================================================================
# 配置加载
# ============================================================================
load_dotenv()
Base = declarative_base()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('./logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# 配置类
# ============================================================================
class Config:
    """Bot configuration"""
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///telegram_bot.db')
    
    # Proxy
    PROXY_ENABLED = os.getenv('PROXY_ENABLED', 'false').lower() == 'true'
    PROXY_TYPE = os.getenv('PROXY_TYPE', 'socks5')
    PROXY_HOST = os.getenv('PROXY_HOST', '127.0.0.1')
    PROXY_PORT = int(os.getenv('PROXY_PORT', 1080))
    PROXY_USERNAME = os.getenv('PROXY_USERNAME', '')
    PROXY_PASSWORD = os.getenv('PROXY_PASSWORD', '')
    
    # Telegram API
    API_ID = os.getenv('API_ID', '')
    API_HASH = os.getenv('API_HASH', '')
    
    # Task settings
    DEFAULT_MIN_INTERVAL = int(os.getenv('DEFAULT_MIN_INTERVAL', 30))
    DEFAULT_MAX_INTERVAL = int(os.getenv('DEFAULT_MAX_INTERVAL', 120))
    DEFAULT_DAILY_LIMIT = int(os.getenv('DEFAULT_DAILY_LIMIT', 50))
    
    # Directories
    SESSIONS_DIR = os.getenv('SESSIONS_DIR', './sessions')
    UPLOADS_DIR = os.getenv('UPLOADS_DIR', './uploads')
    MEDIA_DIR = os.getenv('MEDIA_DIR', './media')
    RESULTS_DIR = os.getenv('RESULTS_DIR', './results')
    LOGS_DIR = os.getenv('LOGS_DIR', './logs')
    
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist"""
        for directory in [cls.SESSIONS_DIR, cls.UPLOADS_DIR, cls.MEDIA_DIR, 
                         cls.RESULTS_DIR, cls.LOGS_DIR]:
            os.makedirs(directory, exist_ok=True)
    
    @classmethod
    def get_proxy_dict(cls):
        """Get proxy configuration"""
        if not cls.PROXY_ENABLED:
            return None
        proxy = {
            'proxy_type': cls.PROXY_TYPE,
            'addr': cls.PROXY_HOST,
            'port': cls.PROXY_PORT
        }
        if cls.PROXY_USERNAME:
            proxy['username'] = cls.PROXY_USERNAME
        if cls.PROXY_PASSWORD:
            proxy['password'] = cls.PROXY_PASSWORD
        return proxy
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        if not cls.ADMIN_USER_ID:
            raise ValueError("ADMIN_USER_ID is required")
        if not cls.API_ID or not cls.API_HASH:
            raise ValueError("API_ID and API_HASH are required")


# ============================================================================
# 枚举类型
# ============================================================================
class AccountStatus(enum.Enum):
    """Account status"""
    ACTIVE = "active"
    BANNED = "banned"
    LIMITED = "limited"
    INACTIVE = "inactive"


class TaskStatus(enum.Enum):
    """Task status"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageFormat(enum.Enum):
    """Message format"""
    PLAIN = "plain"
    MARKDOWN = "markdown"
    HTML = "html"


class MediaType(enum.Enum):
    """Media type"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    DOCUMENT = "document"
    FORWARD = "forward"


# ============================================================================
# 数据库模型
# ============================================================================
class Account(Base):
    """Telegram account model"""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    phone = Column(String(20), unique=True, nullable=False)
    session_name = Column(String(100), unique=True, nullable=False)
    status = Column(SQLEnum(AccountStatus), default=AccountStatus.ACTIVE)
    api_id = Column(String(50))
    api_hash = Column(String(100))
    messages_sent_today = Column(Integer, default=0)
    total_messages_sent = Column(Integer, default=0)
    last_used = Column(DateTime, nullable=True)
    daily_limit = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    tasks = relationship("Task", back_populates="account")
    message_logs = relationship("MessageLog", back_populates="account")


class Task(Base):
    """Task model"""
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    message_text = Column(Text, nullable=False)
    message_format = Column(SQLEnum(MessageFormat), default=MessageFormat.PLAIN)
    media_type = Column(SQLEnum(MediaType), default=MediaType.TEXT)
    media_path = Column(String(500), nullable=True)
    min_interval = Column(Integer, default=30)
    max_interval = Column(Integer, default=120)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    total_targets = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    account = relationship("Account", back_populates="tasks")
    targets = relationship("Target", back_populates="task", cascade="all, delete-orphan")
    message_logs = relationship("MessageLog", back_populates="task", cascade="all, delete-orphan")


class Target(Base):
    """Target user model"""
    __tablename__ = 'targets'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    username = Column(String(100), nullable=True)
    user_id = Column(String(50), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    is_sent = Column(Boolean, default=False)
    is_valid = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    
    task = relationship("Task", back_populates="targets")


class MessageLog(Base):
    """Message log model"""
    __tablename__ = 'message_logs'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    target_id = Column(Integer, ForeignKey('targets.id'), nullable=False)
    message_text = Column(Text, nullable=False)
    success = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    task = relationship("Task", back_populates="message_logs")
    account = relationship("Account", back_populates="message_logs")
    target = relationship("Target")


def init_db(database_url):
    """Initialize database"""
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """Get database session"""
    Session = sessionmaker(bind=engine)
    return Session()


# ============================================================================
# 消息格式化类
# ============================================================================
class MessageFormatter:
    """Format and personalize messages"""
    
    @staticmethod
    def personalize(message_text, user_info):
        """Personalize message with user information"""
        if not user_info:
            return message_text
        
        replacements = {
            '{name}': user_info.get('name', ''),
            '{first_name}': user_info.get('first_name', ''),
            '{last_name}': user_info.get('last_name', ''),
            '{full_name}': user_info.get('full_name', ''),
            '{username}': user_info.get('username', '')
        }
        
        personalized = message_text
        for placeholder, value in replacements.items():
            if value:
                personalized = personalized.replace(placeholder, value)
        return personalized
    
    @staticmethod
    def extract_user_info(user):
        """Extract user information"""
        info = {}
        info['first_name'] = getattr(user, 'first_name', '') or ''
        info['last_name'] = getattr(user, 'last_name', '') or ''
        info['username'] = f"@{user.username}" if getattr(user, 'username', None) else ''
        
        full_name_parts = []
        if info['first_name']:
            full_name_parts.append(info['first_name'])
        if info['last_name']:
            full_name_parts.append(info['last_name'])
        info['full_name'] = ' '.join(full_name_parts)
        info['name'] = info['username'].replace('@', '') if info['username'] else info['first_name']
        
        return info
    
    @staticmethod
    def get_parse_mode(message_format):
        """Get Telethon parse mode"""
        if message_format == MessageFormat.MARKDOWN:
            return 'md'
        elif message_format == MessageFormat.HTML:
            return 'html'
        return None


# ============================================================================
# 账户管理类
# ============================================================================
class AccountManager:
    """Manage Telegram accounts"""
    
    def __init__(self, db_session):
        self.db_session = db_session
        self.clients = {}
    
    async def send_code_request(self, phone, api_id=None, api_hash=None):
        """Send code to phone"""
        api_id = api_id or Config.API_ID
        api_hash = api_hash or Config.API_HASH
        
        session_name = f"session_{phone.replace('+', '')}"
        session_path = os.path.join(Config.SESSIONS_DIR, session_name)
        proxy = Config.get_proxy_dict()
        client = TelegramClient(session_path, api_id, api_hash, proxy=proxy)
        
        try:
            await client.connect()
            result = await client.send_code_request(phone)
            return {
                'status': 'success',
                'phone': phone,
                'client': client,
                'phone_code_hash': result.phone_code_hash
            }
        except Exception as e:
            logger.error(f"Error sending code: {e}")
            if client.is_connected():
                await client.disconnect()
            raise
    
    async def verify_code(self, phone, code, phone_code_hash, client, password=None):
        """Verify phone code"""
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                return {'status': 'password_required', 'client': client}
            await client.sign_in(password=password)
        except PhoneCodeInvalidError:
            raise ValueError("Invalid code")
        
        me = await client.get_me()
        session_name = f"session_{phone.replace('+', '')}"
        account = Account(
            phone=phone,
            session_name=session_name,
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            status=AccountStatus.ACTIVE
        )
        self.db_session.add(account)
        self.db_session.commit()
        self.clients[account.id] = client
        
        return {'status': 'success', 'account': account, 'user': me}
    
    async def import_session_zip(self, zip_path, api_id=None, api_hash=None):
        """Import sessions from zip"""
        logger.info(f"Starting session import from: {zip_path}")
        api_id = api_id or Config.API_ID
        api_hash = api_hash or Config.API_HASH
        imported = []
        temp_dir = os.path.join(Config.UPLOADS_DIR, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        logger.info(f"Created temporary directory: {temp_dir}")
        
        try:
            logger.info(f"Extracting zip file...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            logger.info(f"Zip file extracted successfully")
            
            session_files = []
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.session'):
                        session_files.append(os.path.join(root, file))
            
            logger.info(f"Found {len(session_files)} session files")
            
            for idx, session_path in enumerate(session_files, 1):
                logger.info(f"Verifying session {idx}/{len(session_files)}: {os.path.basename(session_path)}")
                result = await self._verify_session(session_path, api_id, api_hash)
                if result:
                    imported.append(result)
                    logger.info(f"Session verified successfully: {result['account'].phone}")
                else:
                    logger.warning(f"Session verification failed: {os.path.basename(session_path)}")
            
            logger.info(f"Import completed: {len(imported)}/{len(session_files)} sessions imported successfully")
            return imported
        finally:
            logger.info(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    async def _verify_session(self, session_path, api_id, api_hash):
        """Verify session file"""
        logger.info(f"Connecting to Telegram with session: {os.path.basename(session_path)}")
        proxy = Config.get_proxy_dict()
        client = TelegramClient(session_path, api_id, api_hash, proxy=proxy)
        
        try:
            await client.connect()
            logger.info(f"Connected successfully, checking authorization...")
            
            if not await client.is_user_authorized():
                logger.warning(f"Session not authorized: {os.path.basename(session_path)}")
                return None
            
            me = await client.get_me()
            phone = me.phone if me.phone else f"user_{me.id}"
            logger.info(f"User info retrieved: {me.first_name} ({phone})")
            
            session_name = os.path.basename(session_path).replace('.session', '')
            new_path = os.path.join(Config.SESSIONS_DIR, f"{session_name}.session")
            shutil.copy2(session_path, new_path)
            logger.info(f"Session file copied to: {new_path}")
            
            account = Account(
                phone=phone,
                session_name=session_name,
                api_id=str(api_id),
                api_hash=api_hash,
                status=AccountStatus.ACTIVE
            )
            self.db_session.add(account)
            self.db_session.commit()
            logger.info(f"Account saved to database: {phone}")
            
            await client.disconnect()
            
            return {'account': account, 'user': me}
        except Exception as e:
            logger.error(f"Error verifying session {os.path.basename(session_path)}: {e}", exc_info=True)
            if client.is_connected():
                await client.disconnect()
            return None
    
    async def get_client(self, account_id):
        """Get client for account"""
        if account_id in self.clients and self.clients[account_id].is_connected():
            return self.clients[account_id]
        
        account = self.db_session.query(Account).filter_by(id=account_id).first()
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        session_path = os.path.join(Config.SESSIONS_DIR, account.session_name)
        proxy = Config.get_proxy_dict()
        client = TelegramClient(session_path, int(account.api_id), account.api_hash, proxy=proxy)
        
        await client.connect()
        if not await client.is_user_authorized():
            account.status = AccountStatus.INACTIVE
            self.db_session.commit()
            raise ValueError(f"Account {account_id} not authorized")
        
        self.clients[account_id] = client
        return client
    
    async def check_account_status(self, account_id):
        """Check account status"""
        try:
            client = await self.get_client(account_id)
            await client.get_me()
            account = self.db_session.query(Account).filter_by(id=account_id).first()
            account.status = AccountStatus.ACTIVE
            self.db_session.commit()
            return True
        except Exception as e:
            logger.error(f"Error checking account: {e}")
            account = self.db_session.query(Account).filter_by(id=account_id).first()
            if account:
                account.status = AccountStatus.INACTIVE
                self.db_session.commit()
            return False
    
    def get_active_accounts(self):
        """Get active accounts"""
        return self.db_session.query(Account).filter_by(status=AccountStatus.ACTIVE).all()
    
    async def disconnect_all(self):
        """Disconnect all clients"""
        for client in self.clients.values():
            if client.is_connected():
                await client.disconnect()
        self.clients.clear()


# ============================================================================
# 任务管理类
# ============================================================================
class TaskManager:
    """Manage tasks"""
    
    def __init__(self, db_session, account_manager):
        self.db_session = db_session
        self.account_manager = account_manager
        self.running_tasks = {}
        self.stop_flags = {}
    
    def create_task(self, name, message_text, message_format, media_type=MediaType.TEXT,
                   media_path=None, min_interval=30, max_interval=120):
        """Create new task"""
        task = Task(
            name=name,
            message_text=message_text,
            message_format=message_format,
            media_type=media_type,
            media_path=media_path,
            min_interval=min_interval,
            max_interval=max_interval,
            status=TaskStatus.PENDING
        )
        self.db_session.add(task)
        self.db_session.commit()
        return task
    
    def add_targets(self, task_id, target_list):
        """Add targets to task"""
        task = self.db_session.query(Task).filter_by(id=task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        unique_targets = set()
        for target in target_list:
            target = str(target).strip()
            if target.startswith('@'):
                target = target[1:]
            unique_targets.add(target)
        
        added_count = 0
        for target_str in unique_targets:
            if target_str.isdigit():
                target = Target(task_id=task_id, user_id=target_str)
            else:
                target = Target(task_id=task_id, username=target_str)
            self.db_session.add(target)
            added_count += 1
        
        task.total_targets = added_count
        self.db_session.commit()
        return added_count
    
    def parse_target_file(self, file_content):
        """Parse targets from file"""
        lines = file_content.decode('utf-8').split('\n')
        targets = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                targets.append(line)
        return targets
    
    async def start_task(self, task_id):
        """Start task"""
        task = self.db_session.query(Task).filter_by(id=task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task.status == TaskStatus.RUNNING:
            raise ValueError("Task already running")
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        self.db_session.commit()
        
        self.stop_flags[task_id] = False
        asyncio_task = asyncio.create_task(self._execute_task(task_id))
        self.running_tasks[task_id] = asyncio_task
        return asyncio_task
    
    async def stop_task(self, task_id):
        """Stop task"""
        if task_id not in self.running_tasks:
            raise ValueError("Task not running")
        
        self.stop_flags[task_id] = True
        asyncio_task = self.running_tasks[task_id]
        try:
            await asyncio.wait_for(asyncio_task, timeout=10.0)
        except asyncio.TimeoutError:
            asyncio_task.cancel()
        
        task = self.db_session.query(Task).filter_by(id=task_id).first()
        if task:
            task.status = TaskStatus.PAUSED
            self.db_session.commit()
        
        del self.running_tasks[task_id]
        del self.stop_flags[task_id]
    
    async def _execute_task(self, task_id):
        """Execute task"""
        task = self.db_session.query(Task).filter_by(id=task_id).first()
        logger.info(f"Starting task execution: Task ID={task_id}, Name={task.name}")
        
        try:
            targets = self.db_session.query(Target).filter_by(
                task_id=task_id, is_sent=False, is_valid=True
            ).all()
            
            logger.info(f"Task {task_id}: Found {len(targets)} targets to process")
            
            if not targets:
                logger.info(f"Task {task_id}: No targets to process, marking as completed")
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.utcnow()
                self.db_session.commit()
                return
            
            accounts = self.account_manager.get_active_accounts()
            if not accounts:
                logger.error(f"Task {task_id}: No active accounts available")
                raise ValueError("No active accounts")
            
            logger.info(f"Task {task_id}: Using {len(accounts)} active accounts")
            
            account_index = 0
            for idx, target in enumerate(targets, 1):
                if self.stop_flags.get(task_id, False):
                    logger.info(f"Task {task_id}: Stop flag detected, halting execution")
                    break
                
                account = accounts[account_index % len(accounts)]
                account_index += 1
                
                logger.info(f"Task {task_id}: Processing target {idx}/{len(targets)} - {target.username or target.user_id}")
                
                if account.messages_sent_today >= account.daily_limit:
                    logger.warning(f"Task {task_id}: Account {account.phone} reached daily limit, skipping")
                    continue
                
                if account.last_used and account.last_used.date() < datetime.utcnow().date():
                    logger.info(f"Task {task_id}: Resetting daily counter for account {account.phone}")
                    account.messages_sent_today = 0
                
                success = await self._send_message(task, target, account)
                
                if success:
                    task.sent_count += 1
                    account.messages_sent_today += 1
                    account.total_messages_sent += 1
                    logger.info(f"Task {task_id}: Message sent successfully to {target.username or target.user_id}")
                else:
                    task.failed_count += 1
                    logger.warning(f"Task {task_id}: Failed to send message to {target.username or target.user_id}")
                
                account.last_used = datetime.utcnow()
                self.db_session.commit()
                
                delay = random.randint(task.min_interval, task.max_interval)
                logger.info(f"Task {task_id}: Waiting {delay} seconds before next message... ({task.sent_count}/{task.total_targets} sent)")
                await asyncio.sleep(delay)
            
            logger.info(f"Task {task_id}: Execution completed - Sent: {task.sent_count}, Failed: {task.failed_count}")
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            self.db_session.commit()
            
        except Exception as e:
            logger.error(f"Task {task_id} error: {e}", exc_info=True)
            task.status = TaskStatus.FAILED
            self.db_session.commit()
        finally:
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            if task_id in self.stop_flags:
                del self.stop_flags[task_id]
            logger.info(f"Task {task_id}: Cleanup completed")
    
    async def _send_message(self, task, target, account):
        """Send message"""
        try:
            client = await self.account_manager.get_client(account.id)
            
            recipient = int(target.user_id) if target.user_id else target.username
            
            try:
                entity = await client.get_entity(recipient)
            except Exception as e:
                logger.error(f"Failed to get entity {recipient}: {e}")
                target.is_valid = False
                target.error_message = str(e)
                self.db_session.commit()
                self._log_message(task.id, account.id, target.id, task.message_text, False, str(e))
                return False
            
            user_info = MessageFormatter.extract_user_info(entity)
            target.first_name = user_info.get('first_name', '')
            target.last_name = user_info.get('last_name', '')
            
            personalized = MessageFormatter.personalize(task.message_text, user_info)
            parse_mode = MessageFormatter.get_parse_mode(task.message_format)
            
            if task.media_type == MediaType.TEXT:
                await client.send_message(entity, personalized, parse_mode=parse_mode)
            elif task.media_type in [MediaType.IMAGE, MediaType.VIDEO, MediaType.DOCUMENT]:
                await client.send_file(entity, task.media_path, caption=personalized, parse_mode=parse_mode)
            elif task.media_type == MediaType.VOICE:
                await client.send_file(entity, task.media_path, voice_note=True, caption=personalized, parse_mode=parse_mode)
            
            target.is_sent = True
            target.sent_at = datetime.utcnow()
            self.db_session.commit()
            
            self._log_message(task.id, account.id, target.id, personalized, True, None)
            logger.info(f"Message sent to {recipient}")
            return True
            
        except (UserPrivacyRestrictedError, UserIsBlockedError, ChatWriteForbiddenError, UserNotMutualContactError) as e:
            error_msg = f"Privacy error: {type(e).__name__}"
            target.error_message = error_msg
            self.db_session.commit()
            self._log_message(task.id, account.id, target.id, task.message_text, False, error_msg)
            return False
            
        except FloodWaitError as e:
            error_msg = f"FloodWait: {e.seconds}s"
            account.status = AccountStatus.LIMITED
            self.db_session.commit()
            self._log_message(task.id, account.id, target.id, task.message_text, False, error_msg)
            await asyncio.sleep(e.seconds)
            return False
            
        except PeerFloodError:
            error_msg = "PeerFlood"
            account.status = AccountStatus.LIMITED
            self.db_session.commit()
            self._log_message(task.id, account.id, target.id, task.message_text, False, error_msg)
            return False
            
        except Exception as e:
            error_msg = str(e)
            target.error_message = error_msg
            self.db_session.commit()
            self._log_message(task.id, account.id, target.id, task.message_text, False, error_msg)
            return False
    
    def _log_message(self, task_id, account_id, target_id, message_text, success, error_message):
        """Log message"""
        log = MessageLog(
            task_id=task_id,
            account_id=account_id,
            target_id=target_id,
            message_text=message_text,
            success=success,
            error_message=error_message
        )
        self.db_session.add(log)
        self.db_session.commit()
    
    def get_task_progress(self, task_id):
        """Get task progress"""
        task = self.db_session.query(Task).filter_by(id=task_id).first()
        if not task:
            return None
        
        return {
            'task_id': task.id,
            'name': task.name,
            'status': task.status.value,
            'total_targets': task.total_targets,
            'sent_count': task.sent_count,
            'failed_count': task.failed_count,
            'pending_count': task.total_targets - task.sent_count - task.failed_count,
            'progress_percent': (task.sent_count / task.total_targets * 100) if task.total_targets > 0 else 0
        }
    
    def export_task_results(self, task_id):
        """Export results"""
        task = self.db_session.query(Task).filter_by(id=task_id).first()
        if not task:
            return None
        
        success_targets = self.db_session.query(Target).filter_by(task_id=task_id, is_sent=True).all()
        failed_targets = self.db_session.query(Target).filter_by(task_id=task_id, is_sent=False).filter(Target.error_message.isnot(None)).all()
        logs = self.db_session.query(MessageLog).filter_by(task_id=task_id).all()
        
        return {
            'success_targets': success_targets,
            'failed_targets': failed_targets,
            'logs': logs
        }


# ============================================================================
# BOT 界面
# ============================================================================

# Conversation states
(PHONE_INPUT, CODE_INPUT, PASSWORD_INPUT, 
 MESSAGE_INPUT, FORMAT_SELECT, MEDIA_SELECT, MEDIA_UPLOAD,
 TARGET_INPUT, TASK_NAME_INPUT, SESSION_UPLOAD, TDATA_UPLOAD) = range(11)

# Global managers
account_manager = None
task_manager = None
db_session = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "unknown"
    
    logger.info(f"Start command received from user {username} ({user_id})")
    
    if user_id != Config.ADMIN_USER_ID:
        logger.warning(f"Unauthorized access attempt by user {username} ({user_id})")
        await update.message.reply_text("⛔ 未授权访问")
        return
    
    logger.info(f"Authorized user {username} ({user_id}) accessing main menu")
    
    keyboard = [
        [InlineKeyboardButton("📱 账户管理", callback_data='menu_accounts')],
        [InlineKeyboardButton("📝 任务管理", callback_data='menu_tasks')],
        [InlineKeyboardButton("⚙️ 全局配置", callback_data='menu_config')],
        [InlineKeyboardButton("📊 统计信息", callback_data='menu_stats')],
        [InlineKeyboardButton("❓ 帮助", callback_data='menu_help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🤖 <b>Telegram 私信机器人</b>\n\n"
        "欢迎使用 Telegram 批量私信管理系统！\n\n"
        "✅ 多账户管理\n"
        "✅ 富媒体消息\n"
        "✅ 消息个性化\n"
        "✅ 智能防封策略\n"
        "✅ 实时进度监控\n\n"
        "请选择一个选项："
    )
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    username = query.from_user.username or "unknown"
    
    logger.info(f"Button clicked by user {username} ({user_id}): {data}")
    
    # Main menu
    if data == 'menu_accounts':
        logger.info(f"User {user_id} accessing accounts menu")
        await show_accounts_menu(query)
    elif data == 'menu_tasks':
        logger.info(f"User {user_id} accessing tasks menu")
        await show_tasks_menu(query)
    elif data == 'menu_config':
        logger.info(f"User {user_id} accessing config menu")
        await show_config(query)
    elif data == 'menu_stats':
        logger.info(f"User {user_id} accessing stats menu")
        await show_stats(query)
    elif data == 'menu_help':
        logger.info(f"User {user_id} accessing help menu")
        await show_help(query)
    
    # Accounts
    elif data == 'accounts_list':
        logger.info(f"User {user_id} viewing accounts list")
        await list_accounts(query)
    elif data == 'accounts_add':
        logger.info(f"User {user_id} initiating account add")
        await show_add_account_menu(query)
    elif data == 'accounts_add_session':
        logger.info(f"User {user_id} selecting session upload option")
        await show_upload_type_menu(query)
    # Note: upload_session_file and upload_tdata_file are handled by ConversationHandler
    elif data.startswith('account_check_'):
        account_id = int(data.split('_')[2])
        logger.info(f"User {user_id} checking account {account_id}")
        await check_account(query, account_id)
    
    # Tasks
    elif data == 'tasks_list':
        logger.info(f"User {user_id} viewing tasks list")
        await list_tasks(query)
    elif data == 'tasks_create':
        logger.info(f"User {user_id} starting task creation")
        await start_create_task(query, context)
    elif data.startswith('task_start_'):
        task_id = int(data.split('_')[2])
        logger.info(f"User {user_id} starting task {task_id}")
        await start_task_handler(query, task_id)
    elif data.startswith('task_stop_'):
        task_id = int(data.split('_')[2])
        logger.info(f"User {user_id} stopping task {task_id}")
        await stop_task_handler(query, task_id)
    elif data.startswith('task_progress_'):
        task_id = int(data.split('_')[2])
        logger.info(f"User {user_id} viewing task {task_id} progress")
        await show_task_progress(query, task_id)
    elif data.startswith('task_export_'):
        task_id = int(data.split('_')[2])
        logger.info(f"User {user_id} exporting task {task_id} results")
        await export_results(query, task_id)
    
    # Format selection
    elif data.startswith('format_'):
        format_name = data.split('_')[1]
        context.user_data['message_format'] = MessageFormat[format_name.upper()]
        logger.info(f"User {user_id} selected format: {format_name}")
        await select_media_type(query)
    
    # Media selection
    elif data.startswith('media_'):
        media_name = data.split('_')[1]
        context.user_data['media_type'] = MediaType[media_name.upper()]
        logger.info(f"User {user_id} selected media type: {media_name}")
        if context.user_data['media_type'] == MediaType.TEXT:
            await request_target_list(query)
        else:
            await request_media_upload(query)
    
    # Back
    elif data == 'back_main':
        logger.info(f"User {user_id} returning to main menu")
        await back_to_main(query)


async def show_accounts_menu(query):
    """Show accounts menu"""
    keyboard = [
        [InlineKeyboardButton("📋 查看账户列表", callback_data='accounts_list')],
        [InlineKeyboardButton("➕ 添加账户", callback_data='accounts_add')],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data='back_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📱 <b>账户管理</b>\n\n请选择操作："
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def show_add_account_menu(query):
    """Show add account menu"""
    keyboard = [
        [InlineKeyboardButton("📁 上传 Session 文件", callback_data='accounts_add_session')],
        [InlineKeyboardButton("🔙 返回", callback_data='menu_accounts')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "➕ <b>添加账户</b>\n\n"
        "上传 Session 文件：\n"
        "支持 .session、session+json、tdata 格式\n"
        "请打包为 .zip 文件上传"
    )
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def show_upload_type_menu(query):
    """Show upload type menu"""
    logger.info(f"User {query.from_user.id} requested upload type menu")
    keyboard = [
        [InlineKeyboardButton("📁 上传 Session 文件", callback_data='upload_session_file')],
        [InlineKeyboardButton("📂 上传 TData 文件", callback_data='upload_tdata_file')],
        [InlineKeyboardButton("🔙 返回", callback_data='accounts_add')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "📁 <b>上传文件</b>\n\n"
        "请选择上传类型：\n\n"
        "📁 <b>Session 文件</b>\n"
        "支持 .session、session+json 格式\n"
        "请打包为 .zip 文件上传\n\n"
        "📂 <b>TData 文件</b>\n"
        "Telegram Desktop 的 tdata 文件夹\n"
        "请打包为 .zip 文件上传"
    )
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def request_session_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Request session file upload - Conversation entry point.
    
    Handles the upload_session_file callback, prompts the user to upload a .zip file
    containing session files, and transitions to SESSION_UPLOAD state.
    
    Returns:
        int: SESSION_UPLOAD state constant
    """
    query = update.callback_query
    await query.answer()
    logger.info(f"User {query.from_user.id} requested session file upload")
    context.user_data['upload_type'] = 'session'
    await query.message.reply_text(
        "📁 <b>上传 Session 文件</b>\n\n"
        "请上传包含 Session 文件的 .zip 压缩包\n"
        "支持格式：\n"
        "- .session 文件\n"
        "- .session + .json 文件\n\n"
        "⚠️ 文件大小限制：50MB",
        parse_mode='HTML'
    )
    return SESSION_UPLOAD


async def request_tdata_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Request TData file upload - Conversation entry point.
    
    Handles the upload_tdata_file callback, prompts the user to upload a .zip file
    containing Telegram Desktop tdata folder, and transitions to TDATA_UPLOAD state.
    
    Returns:
        int: TDATA_UPLOAD state constant
    """
    query = update.callback_query
    await query.answer()
    logger.info(f"User {query.from_user.id} requested tdata file upload")
    context.user_data['upload_type'] = 'tdata'
    await query.message.reply_text(
        "📂 <b>上传 TData 文件</b>\n\n"
        "请上传 Telegram Desktop 的 tdata 文件夹压缩包\n"
        "格式：tdata 文件夹打包为 .zip\n\n"
        "⚠️ 文件大小限制：50MB",
        parse_mode='HTML'
    )
    return TDATA_UPLOAD


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file upload for session or tdata"""
    upload_type = context.user_data.get('upload_type', 'session')
    # Determine which state to return based on upload type
    current_state = SESSION_UPLOAD if upload_type == 'session' else TDATA_UPLOAD
    
    logger.info(f"User {update.effective_user.id} is uploading {upload_type} file")
    
    if not update.message.document:
        logger.warning(f"User {update.effective_user.id} sent non-document message")
        await update.message.reply_text("❌ 请上传 .zip 文件")
        return current_state
    
    document = update.message.document
    if not document.file_name.endswith('.zip'):
        logger.warning(f"User {update.effective_user.id} uploaded non-zip file: {document.file_name}")
        await update.message.reply_text("❌ 只支持 .zip 格式文件")
        return current_state
    
    # Download file
    logger.info(f"Downloading file: {document.file_name} ({document.file_size} bytes)")
    await update.message.reply_text("⏳ 正在下载文件...")
    
    try:
        file = await document.get_file()
        zip_path = os.path.join(Config.UPLOADS_DIR, f"{update.effective_user.id}_{document.file_name}")
        await file.download_to_drive(zip_path)
        logger.info(f"File downloaded successfully: {zip_path}")
        
        await update.message.reply_text("⏳ 正在导入账户...")
        logger.info(f"Starting account import from: {zip_path}")
        
        # Import accounts
        imported = await account_manager.import_session_zip(zip_path)
        
        if not imported:
            logger.warning(f"No accounts imported from {zip_path}")
            await update.message.reply_text(
                "❌ <b>导入失败</b>\n\n"
                "未找到有效的账户文件\n"
                "请检查 .zip 文件内容",
                parse_mode='HTML'
            )
        else:
            logger.info(f"Successfully imported {len(imported)} accounts")
            accounts_info = "\n".join([
                f"• {result['user'].first_name or ''} ({result['account'].phone})"
                for result in imported
            ])
            await update.message.reply_text(
                f"✅ <b>导入成功！</b>\n\n"
                f"成功导入 {len(imported)} 个账户：\n\n"
                f"{accounts_info}\n\n"
                f"使用 /start 查看账户列表",
                parse_mode='HTML'
            )
        
        # Cleanup
        try:
            os.remove(zip_path)
            logger.info(f"Cleaned up temporary file: {zip_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup file {zip_path}: {e}")
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error importing accounts: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ <b>导入失败</b>\n\n"
            f"错误：{str(e)}\n\n"
            f"请检查文件格式是否正确",
            parse_mode='HTML'
        )
        return current_state


async def list_accounts(query):
    """List accounts"""
    accounts = db_session.query(Account).all()
    
    if not accounts:
        text = "📱 <b>账户列表</b>\n\n暂无账户"
        keyboard = [
            [InlineKeyboardButton("➕ 添加账户", callback_data='accounts_add')],
            [InlineKeyboardButton("🔙 返回", callback_data='menu_accounts')]
        ]
    else:
        text = f"📱 <b>账户列表</b>\n\n共 {len(accounts)} 个账户：\n\n"
        keyboard = []
        
        for account in accounts:
            status_emoji = {'active': '✅', 'banned': '🚫', 'limited': '⚠️', 'inactive': '❌'}.get(account.status.value, '❓')
            text += (
                f"{status_emoji} <b>{account.phone}</b>\n"
                f"   状态: {account.status.value}\n"
                f"   今日: {account.messages_sent_today}/{account.daily_limit}\n\n"
            )
            keyboard.append([InlineKeyboardButton(f"检查 {account.phone}", callback_data=f'account_check_{account.id}')])
        
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data='menu_accounts')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def check_account(query, account_id):
    """Check account"""
    result = await account_manager.check_account_status(account_id)
    if result:
        await query.message.reply_text("✅ 账户正常")
    else:
        await query.message.reply_text("❌ 账户异常")


async def show_tasks_menu(query):
    """Show tasks menu"""
    keyboard = [
        [InlineKeyboardButton("📋 查看任务列表", callback_data='tasks_list')],
        [InlineKeyboardButton("➕ 创建新任务", callback_data='tasks_create')],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data='back_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📝 <b>任务管理</b>\n\n请选择操作："
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def list_tasks(query):
    """List tasks"""
    tasks = db_session.query(Task).all()
    
    if not tasks:
        text = "📝 <b>任务列表</b>\n\n暂无任务"
        keyboard = [
            [InlineKeyboardButton("➕ 创建新任务", callback_data='tasks_create')],
            [InlineKeyboardButton("🔙 返回", callback_data='menu_tasks')]
        ]
    else:
        text = f"📝 <b>任务列表</b>\n\n共 {len(tasks)} 个任务：\n\n"
        keyboard = []
        
        for task in tasks:
            status_emoji = {'pending': '⏳', 'running': '▶️', 'paused': '⏸️', 'completed': '✅', 'failed': '❌'}.get(task.status.value, '❓')
            progress = (task.sent_count / task.total_targets * 100) if task.total_targets > 0 else 0
            
            text += (
                f"{status_emoji} <b>{task.name}</b>\n"
                f"   进度: {task.sent_count}/{task.total_targets} ({progress:.1f}%)\n\n"
            )
            
            buttons = []
            if task.status in [TaskStatus.PENDING, TaskStatus.PAUSED]:
                buttons.append(InlineKeyboardButton("▶️ 开始", callback_data=f'task_start_{task.id}'))
            elif task.status == TaskStatus.RUNNING:
                buttons.append(InlineKeyboardButton("⏸️ 停止", callback_data=f'task_stop_{task.id}'))
            buttons.append(InlineKeyboardButton("📊 进度", callback_data=f'task_progress_{task.id}'))
            if task.status == TaskStatus.COMPLETED:
                buttons.append(InlineKeyboardButton("📥 导出", callback_data=f'task_export_{task.id}'))
            keyboard.append(buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data='menu_tasks')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def start_create_task(query, context):
    """Start task creation"""
    await query.message.reply_text("➕ <b>创建新任务</b>\n\n请输入任务名称：", parse_mode='HTML')
    context.user_data['creating_task'] = True
    return TASK_NAME_INPUT


async def handle_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task name"""
    context.user_data['task_name'] = update.message.text
    await update.message.reply_text(
        f"✅ 任务名称: <b>{update.message.text}</b>\n\n"
        "请输入消息内容：\n\n"
        "💡 可使用变量：{name}, {first_name}, {last_name}, {full_name}, {username}",
        parse_mode='HTML'
    )
    return MESSAGE_INPUT


async def handle_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle message input"""
    context.user_data['message_text'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("📝 纯文本", callback_data='format_plain')],
        [InlineKeyboardButton("📌 Markdown", callback_data='format_markdown')],
        [InlineKeyboardButton("🏷️ HTML", callback_data='format_html')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("✅ 消息已保存\n\n请选择格式：", reply_markup=reply_markup)
    return FORMAT_SELECT


async def select_media_type(query):
    """Select media type"""
    keyboard = [
        [InlineKeyboardButton("📝 纯文本", callback_data='media_text')],
        [InlineKeyboardButton("🖼️ 图片", callback_data='media_image')],
        [InlineKeyboardButton("🎥 视频", callback_data='media_video')],
        [InlineKeyboardButton("📄 文档", callback_data='media_document')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("请选择媒体类型：", reply_markup=reply_markup)
    return MEDIA_SELECT


async def request_media_upload(query):
    """Request media upload"""
    await query.message.reply_text("请上传媒体文件：")
    return MEDIA_UPLOAD


async def request_target_list(query):
    """Request target list"""
    await query.message.reply_text(
        "✅ 配置完成\n\n"
        "请发送目标列表：\n"
        "1️⃣ 直接发送（每行一个）\n"
        "2️⃣ 上传 .txt 文件\n\n"
        "格式：@username 或 用户ID"
    )
    return TARGET_INPUT


async def handle_target_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle target input"""
    if update.message.text:
        targets = update.message.text.strip().split('\n')
    elif update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        targets = task_manager.parse_target_file(bytes(content))
    else:
        await update.message.reply_text("❌ 无效输入")
        return TARGET_INPUT
    
    task = task_manager.create_task(
        name=context.user_data['task_name'],
        message_text=context.user_data['message_text'],
        message_format=context.user_data['message_format'],
        media_type=context.user_data.get('media_type', MediaType.TEXT),
        media_path=context.user_data.get('media_path'),
        min_interval=Config.DEFAULT_MIN_INTERVAL,
        max_interval=Config.DEFAULT_MAX_INTERVAL
    )
    
    added = task_manager.add_targets(task.id, targets)
    
    await update.message.reply_text(
        f"✅ <b>任务创建成功！</b>\n\n"
        f"任务: {task.name}\n"
        f"目标: {added}\n\n"
        f"使用 /start 查看任务",
        parse_mode='HTML'
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def start_task_handler(query, task_id):
    """Start task"""
    try:
        await task_manager.start_task(task_id)
        await query.message.reply_text("✅ 任务已开始")
    except Exception as e:
        await query.message.reply_text(f"❌ 失败: {str(e)}")


async def stop_task_handler(query, task_id):
    """Stop task"""
    try:
        await task_manager.stop_task(task_id)
        await query.message.reply_text("⏸️ 任务已停止")
    except Exception as e:
        await query.message.reply_text(f"❌ 失败: {str(e)}")


async def show_task_progress(query, task_id):
    """Show progress"""
    progress = task_manager.get_task_progress(task_id)
    if not progress:
        await query.message.reply_text("❌ 任务不存在")
        return
    
    text = (
        f"📊 <b>任务进度</b>\n\n"
        f"任务: {progress['name']}\n"
        f"状态: {progress['status']}\n\n"
        f"总数: {progress['total_targets']}\n"
        f"已发送: {progress['sent_count']}\n"
        f"失败: {progress['failed_count']}\n"
        f"待发送: {progress['pending_count']}\n"
        f"进度: {progress['progress_percent']:.1f}%"
    )
    await query.message.reply_text(text, parse_mode='HTML')


async def export_results(query, task_id):
    """Export results"""
    results = task_manager.export_task_results(task_id)
    if not results:
        await query.message.reply_text("❌ 任务不存在")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    success_file = os.path.join(Config.RESULTS_DIR, f"success_{task_id}_{timestamp}.txt")
    with open(success_file, 'w', encoding='utf-8') as f:
        for t in results['success_targets']:
            f.write(f"{t.username or t.user_id}\n")
    
    failed_file = os.path.join(Config.RESULTS_DIR, f"failed_{task_id}_{timestamp}.txt")
    with open(failed_file, 'w', encoding='utf-8') as f:
        for t in results['failed_targets']:
            f.write(f"{t.username or t.user_id}: {t.error_message}\n")
    
    log_file = os.path.join(Config.RESULTS_DIR, f"log_{task_id}_{timestamp}.txt")
    with open(log_file, 'w', encoding='utf-8') as f:
        for log in results['logs']:
            status = "成功" if log.success else "失败"
            f.write(f"[{log.sent_at}] {status}: {log.error_message or 'OK'}\n")
    
    await query.message.reply_document(document=open(success_file, 'rb'), filename="success.txt")
    await query.message.reply_document(document=open(failed_file, 'rb'), filename="failed.txt")
    await query.message.reply_document(document=open(log_file, 'rb'), filename="log.txt")
    await query.message.reply_text("✅ 结果已导出")


async def show_config(query):
    """Show config"""
    text = (
        "⚙️ <b>全局配置</b>\n\n"
        f"⏱️ 最小间隔: {Config.DEFAULT_MIN_INTERVAL}s\n"
        f"⏱️ 最大间隔: {Config.DEFAULT_MAX_INTERVAL}s\n"
        f"📮 每日限制: {Config.DEFAULT_DAILY_LIMIT}\n"
        f"🌐 代理: {'启用' if Config.PROXY_ENABLED else '禁用'}\n\n"
        "修改请编辑 .env 文件"
    )
    keyboard = [[InlineKeyboardButton("🔙 返回", callback_data='back_main')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def show_stats(query):
    """Show stats"""
    total_accounts = db_session.query(Account).count()
    active_accounts = db_session.query(Account).filter_by(status=AccountStatus.ACTIVE).count()
    total_tasks = db_session.query(Task).count()
    completed_tasks = db_session.query(Task).filter_by(status=TaskStatus.COMPLETED).count()
    total_msgs = db_session.query(MessageLog).count()
    success_msgs = db_session.query(MessageLog).filter_by(success=True).count()
    
    text = (
        "📊 <b>统计信息</b>\n\n"
        f"📱 账户: {active_accounts}/{total_accounts}\n"
        f"📝 任务: {completed_tasks}/{total_tasks}\n"
        f"📨 消息: {success_msgs}/{total_msgs}\n"
        f"成功率: {(success_msgs/total_msgs*100):.1f}%" if total_msgs > 0 else "成功率: 0%"
    )
    keyboard = [[InlineKeyboardButton("🔙 返回", callback_data='back_main')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def show_help(query):
    """Show help"""
    text = (
        "❓ <b>帮助</b>\n\n"
        "<b>快速开始：</b>\n"
        "1️⃣ 添加账户\n"
        "2️⃣ 创建任务\n"
        "3️⃣ 配置消息\n"
        "4️⃣ 开始任务\n"
        "5️⃣ 查看进度\n"
        "6️⃣ 导出结果\n\n"
        "<b>变量：</b>\n"
        "{name}, {first_name}, {last_name}, {full_name}, {username}"
    )
    keyboard = [[InlineKeyboardButton("🔙 返回", callback_data='back_main')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def back_to_main(query):
    """Back to main"""
    keyboard = [
        [InlineKeyboardButton("📱 账户管理", callback_data='menu_accounts')],
        [InlineKeyboardButton("📝 任务管理", callback_data='menu_tasks')],
        [InlineKeyboardButton("⚙️ 全局配置", callback_data='menu_config')],
        [InlineKeyboardButton("📊 统计信息", callback_data='menu_stats')],
        [InlineKeyboardButton("❓ 帮助", callback_data='menu_help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "🤖 <b>主菜单</b>\n\n请选择："
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


# ============================================================================
# MAIN
# ============================================================================
def main():
    """Main function"""
    global account_manager, task_manager, db_session
    
    logger.info("=" * 80)
    logger.info("Starting Telegram Bot")
    logger.info("=" * 80)
    
    try:
        logger.info("Validating configuration...")
        Config.validate()
        logger.info("Configuration validated successfully")
        
        logger.info("Ensuring directories exist...")
        Config.ensure_directories()
        logger.info("Directories created/verified")
    except ValueError as e:
        logger.error(f"Config error: {e}")
        return
    
    logger.info(f"Initializing database: {Config.DATABASE_URL}")
    engine = init_db(Config.DATABASE_URL)
    db_session = get_session(engine)
    logger.info("Database initialized successfully")
    
    logger.info("Initializing account manager...")
    account_manager = AccountManager(db_session)
    logger.info("Account manager initialized")
    
    logger.info("Initializing task manager...")
    task_manager = TaskManager(db_session, account_manager)
    logger.info("Task manager initialized")
    
    logger.info("Building bot application...")
    application = Application.builder().token(Config.BOT_TOKEN).build()
    
    logger.info("Registering command handlers...")
    application.add_handler(CommandHandler("start", start))
    
    # File upload conversation handler (registered BEFORE button_handler to catch specific callbacks first)
    logger.info("Registering file upload conversation handler...")
    upload_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(request_session_upload, pattern='^upload_session_file$'),
            CallbackQueryHandler(request_tdata_upload, pattern='^upload_tdata_file$')
        ],
        states={
            SESSION_UPLOAD: [MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_file_upload)],
            TDATA_UPLOAD: [MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_file_upload)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    application.add_handler(upload_conv)
    
    # Task creation conversation handler
    logger.info("Registering task conversation handler...")
    task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_create_task, pattern='^tasks_create$')],
        states={
            TASK_NAME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_task_name)],
            MESSAGE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_input)],
            FORMAT_SELECT: [CallbackQueryHandler(button_handler)],
            MEDIA_SELECT: [CallbackQueryHandler(button_handler)],
            TARGET_INPUT: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, handle_target_input)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    application.add_handler(task_conv)
    
    # General button handler (registered AFTER conversation handlers)
    logger.info("Registering general button handler...")
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("=" * 80)
    logger.info("Bot started successfully! Listening for updates...")
    logger.info("=" * 80)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

