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
from pymongo import MongoClient
from bson import ObjectId

# ============================================================================
# 配置加载
# ============================================================================
load_dotenv()

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
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'telegram_bot')
    
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


class SendMethod(enum.Enum):
    """Send method"""
    DIRECT = "direct"  # 直接发送
    POSTBOT = "postbot"  # post代码（使用@postbot配置）
    CHANNEL_FORWARD = "channel_forward"  # 频道转发
    CHANNEL_FORWARD_HIDDEN = "channel_forward_hidden"  # 隐藏转发来源


# ============================================================================
# 常量
# ============================================================================
# Postbot code validation
POSTBOT_CODE_MIN_LENGTH = 10
POSTBOT_RESPONSE_WAIT_SECONDS = 2

# Task execution timing
PROGRESS_MONITOR_INTERVAL = 10
TASK_STOP_TIMEOUT_SECONDS = 2.0
CONFIG_MESSAGE_DELETE_DELAY = 3

# UI labels mapping
SEND_METHOD_LABELS = {
    SendMethod.DIRECT: '📤 直接发送',
    SendMethod.POSTBOT: '🤖 Post代码',
    SendMethod.CHANNEL_FORWARD: '📢 频道转发',
    SendMethod.CHANNEL_FORWARD_HIDDEN: '🔒 隐藏转发来源'
}

MEDIA_TYPE_LABELS = {
    MediaType.TEXT: '📝 纯文本',
    MediaType.IMAGE: '🖼️ 图片',
    MediaType.VIDEO: '🎥 视频',
    MediaType.DOCUMENT: '📄 文档',
    MediaType.FORWARD: '📡 转发'
}


# ============================================================================
# 数据库模型
# ============================================================================
class Account:
    """Telegram account model - MongoDB document"""
    COLLECTION_NAME = 'accounts'
    
    def __init__(self, phone, session_name, status=None, api_id=None, api_hash=None,
                 messages_sent_today=0, total_messages_sent=0, last_used=None,
                 daily_limit=50, created_at=None, updated_at=None, _id=None):
        self._id = _id
        self.phone = phone
        self.session_name = session_name
        self.status = status or AccountStatus.ACTIVE.value
        self.api_id = api_id
        self.api_hash = api_hash
        self.messages_sent_today = messages_sent_today
        self.total_messages_sent = total_messages_sent
        self.last_used = last_used
        self.daily_limit = daily_limit
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
    
    def to_dict(self):
        """Convert to dictionary for MongoDB"""
        doc = {
            'phone': self.phone,
            'session_name': self.session_name,
            'status': self.status,
            'api_id': self.api_id,
            'api_hash': self.api_hash,
            'messages_sent_today': self.messages_sent_today,
            'total_messages_sent': self.total_messages_sent,
            'last_used': self.last_used,
            'daily_limit': self.daily_limit,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
        if self._id:
            doc['_id'] = self._id
        return doc
    
    @classmethod
    def from_dict(cls, doc):
        """Create instance from MongoDB document"""
        if not doc:
            return None
        return cls(
            phone=doc.get('phone'),
            session_name=doc.get('session_name'),
            status=doc.get('status'),
            api_id=doc.get('api_id'),
            api_hash=doc.get('api_hash'),
            messages_sent_today=doc.get('messages_sent_today', 0),
            total_messages_sent=doc.get('total_messages_sent', 0),
            last_used=doc.get('last_used'),
            daily_limit=doc.get('daily_limit', 50),
            created_at=doc.get('created_at'),
            updated_at=doc.get('updated_at'),
            _id=doc.get('_id')
        )


class Task:
    """Task model - MongoDB document"""
    COLLECTION_NAME = 'tasks'
    
    def __init__(self, name, message_text, status=None, message_format=None, 
                 media_type=None, media_path=None, send_method=None, postbot_code=None,
                 channel_link=None, min_interval=30, max_interval=120, account_id=None,
                 total_targets=0, sent_count=0, failed_count=0, created_at=None,
                 started_at=None, completed_at=None, updated_at=None, _id=None,
                 thread_count=1, pin_message=False, delete_dialog=False, 
                 repeat_send=False, ignore_bidirectional_limit=0):
        self._id = _id
        self.name = name
        self.status = status or TaskStatus.PENDING.value
        self.message_text = message_text
        self.message_format = message_format or MessageFormat.PLAIN.value
        self.media_type = media_type or MediaType.TEXT.value
        self.media_path = media_path
        self.send_method = send_method or SendMethod.DIRECT.value
        self.postbot_code = postbot_code
        self.channel_link = channel_link
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.account_id = account_id
        self.total_targets = total_targets
        self.sent_count = sent_count
        self.failed_count = failed_count
        self.created_at = created_at or datetime.utcnow()
        self.started_at = started_at
        self.completed_at = completed_at
        self.updated_at = updated_at or datetime.utcnow()
        # New configuration options
        self.thread_count = thread_count
        self.pin_message = pin_message
        self.delete_dialog = delete_dialog
        self.repeat_send = repeat_send
        self.ignore_bidirectional_limit = ignore_bidirectional_limit
    
    def to_dict(self):
        """Convert to dictionary for MongoDB"""
        doc = {
            'name': self.name,
            'status': self.status,
            'message_text': self.message_text,
            'message_format': self.message_format,
            'media_type': self.media_type,
            'media_path': self.media_path,
            'send_method': self.send_method,
            'postbot_code': self.postbot_code,
            'channel_link': self.channel_link,
            'min_interval': self.min_interval,
            'max_interval': self.max_interval,
            'account_id': self.account_id,
            'total_targets': self.total_targets,
            'sent_count': self.sent_count,
            'failed_count': self.failed_count,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'updated_at': self.updated_at,
            'thread_count': self.thread_count,
            'pin_message': self.pin_message,
            'delete_dialog': self.delete_dialog,
            'repeat_send': self.repeat_send,
            'ignore_bidirectional_limit': self.ignore_bidirectional_limit
        }
        if self._id:
            doc['_id'] = self._id
        return doc
    
    @classmethod
    def from_dict(cls, doc):
        """Create instance from MongoDB document"""
        if not doc:
            return None
        return cls(
            name=doc.get('name'),
            message_text=doc.get('message_text'),
            status=doc.get('status'),
            message_format=doc.get('message_format'),
            media_type=doc.get('media_type'),
            media_path=doc.get('media_path'),
            send_method=doc.get('send_method'),
            postbot_code=doc.get('postbot_code'),
            channel_link=doc.get('channel_link'),
            min_interval=doc.get('min_interval', 30),
            max_interval=doc.get('max_interval', 120),
            account_id=doc.get('account_id'),
            total_targets=doc.get('total_targets', 0),
            sent_count=doc.get('sent_count', 0),
            failed_count=doc.get('failed_count', 0),
            created_at=doc.get('created_at'),
            started_at=doc.get('started_at'),
            completed_at=doc.get('completed_at'),
            updated_at=doc.get('updated_at'),
            _id=doc.get('_id'),
            thread_count=doc.get('thread_count', 1),
            pin_message=doc.get('pin_message', False),
            delete_dialog=doc.get('delete_dialog', False),
            repeat_send=doc.get('repeat_send', False),
            ignore_bidirectional_limit=doc.get('ignore_bidirectional_limit', 0)
        )


class Target:
    """Target user model - MongoDB document"""
    COLLECTION_NAME = 'targets'
    
    def __init__(self, task_id, username=None, user_id=None, first_name=None,
                 last_name=None, is_sent=False, is_valid=True, error_message=None,
                 created_at=None, sent_at=None, _id=None):
        self._id = _id
        self.task_id = task_id
        self.username = username
        self.user_id = user_id
        self.first_name = first_name
        self.last_name = last_name
        self.is_sent = is_sent
        self.is_valid = is_valid
        self.error_message = error_message
        self.created_at = created_at or datetime.utcnow()
        self.sent_at = sent_at
    
    def to_dict(self):
        """Convert to dictionary for MongoDB"""
        doc = {
            'task_id': self.task_id,
            'username': self.username,
            'user_id': self.user_id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'is_sent': self.is_sent,
            'is_valid': self.is_valid,
            'error_message': self.error_message,
            'created_at': self.created_at,
            'sent_at': self.sent_at
        }
        if self._id:
            doc['_id'] = self._id
        return doc
    
    @classmethod
    def from_dict(cls, doc):
        """Create instance from MongoDB document"""
        if not doc:
            return None
        return cls(
            task_id=doc.get('task_id'),
            username=doc.get('username'),
            user_id=doc.get('user_id'),
            first_name=doc.get('first_name'),
            last_name=doc.get('last_name'),
            is_sent=doc.get('is_sent', False),
            is_valid=doc.get('is_valid', True),
            error_message=doc.get('error_message'),
            created_at=doc.get('created_at'),
            sent_at=doc.get('sent_at'),
            _id=doc.get('_id')
        )


class MessageLog:
    """Message log model - MongoDB document"""
    COLLECTION_NAME = 'message_logs'
    
    def __init__(self, task_id, account_id, target_id, message_text,
                 success=False, error_message=None, sent_at=None, _id=None):
        self._id = _id
        self.task_id = task_id
        self.account_id = account_id
        self.target_id = target_id
        self.message_text = message_text
        self.success = success
        self.error_message = error_message
        self.sent_at = sent_at or datetime.utcnow()
    
    def to_dict(self):
        """Convert to dictionary for MongoDB"""
        doc = {
            'task_id': self.task_id,
            'account_id': self.account_id,
            'target_id': self.target_id,
            'message_text': self.message_text,
            'success': self.success,
            'error_message': self.error_message,
            'sent_at': self.sent_at
        }
        if self._id:
            doc['_id'] = self._id
        return doc
    
    @classmethod
    def from_dict(cls, doc):
        """Create instance from MongoDB document"""
        if not doc:
            return None
        return cls(
            task_id=doc.get('task_id'),
            account_id=doc.get('account_id'),
            target_id=doc.get('target_id'),
            message_text=doc.get('message_text'),
            success=doc.get('success', False),
            error_message=doc.get('error_message'),
            sent_at=doc.get('sent_at'),
            _id=doc.get('_id')
        )


def init_db(mongodb_uri, database_name):
    """Initialize MongoDB database"""
    client = MongoClient(mongodb_uri)
    db = client[database_name]
    
    # Create indexes for better performance
    db[Account.COLLECTION_NAME].create_index('phone', unique=True)
    db[Account.COLLECTION_NAME].create_index('session_name', unique=True)
    db[Account.COLLECTION_NAME].create_index('status')
    
    db[Task.COLLECTION_NAME].create_index('status')
    db[Task.COLLECTION_NAME].create_index('account_id')
    
    db[Target.COLLECTION_NAME].create_index('task_id')
    db[Target.COLLECTION_NAME].create_index('is_sent')
    db[Target.COLLECTION_NAME].create_index([('task_id', 1), ('is_sent', 1)])
    
    db[MessageLog.COLLECTION_NAME].create_index('task_id')
    db[MessageLog.COLLECTION_NAME].create_index('account_id')
    db[MessageLog.COLLECTION_NAME].create_index('sent_at')
    
    return db


def get_db_client(mongodb_uri, database_name):
    """Get MongoDB database client"""
    client = MongoClient(mongodb_uri)
    return client[database_name]


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
    
    def __init__(self, db):
        self.db = db
        self.accounts_col = db[Account.COLLECTION_NAME]
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
            status=AccountStatus.ACTIVE.value
        )
        result = self.accounts_col.insert_one(account.to_dict())
        account._id = result.inserted_id
        self.clients[str(account._id)] = client
        
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
            
            # 确保状态设置为 ACTIVE
            account = Account(
                phone=phone,
                session_name=session_name,
                api_id=str(api_id),
                api_hash=api_hash,
                status=AccountStatus.ACTIVE.value  # 明确设置为 ACTIVE
            )
            result = self.accounts_col.insert_one(account.to_dict())
            account._id = result.inserted_id
            logger.info(f"Account saved to database: {phone} with status: {account.status}")
            
            # 验证状态
            saved_account = self.accounts_col.find_one({'_id': result.inserted_id})
            if saved_account['status'] != AccountStatus.ACTIVE.value:
                logger.warning(f"Account {phone} status is not active after save: {saved_account['status']}")
            
            await client.disconnect()
            
            return {'account': account, 'user': me}
        except Exception as e:
            logger.error(f"Error verifying session {os.path.basename(session_path)}: {e}", exc_info=True)
            if client.is_connected():
                await client.disconnect()
            return None
    
    async def get_client(self, account_id):
        """Get client for account"""
        account_id_str = str(account_id)
        if account_id_str in self.clients and self.clients[account_id_str].is_connected():
            return self.clients[account_id_str]
        
        account_doc = self.accounts_col.find_one({'_id': ObjectId(account_id)})
        if not account_doc:
            raise ValueError(f"Account {account_id} not found")
        
        account = Account.from_dict(account_doc)
        session_path = os.path.join(Config.SESSIONS_DIR, account.session_name)
        proxy = Config.get_proxy_dict()
        client = TelegramClient(session_path, int(account.api_id), account.api_hash, proxy=proxy)
        
        await client.connect()
        if not await client.is_user_authorized():
            self.accounts_col.update_one(
                {'_id': ObjectId(account_id)},
                {'$set': {'status': AccountStatus.INACTIVE.value, 'updated_at': datetime.utcnow()}}
            )
            raise ValueError(f"Account {account_id} not authorized")
        
        self.clients[account_id_str] = client
        return client
    
    async def check_account_status(self, account_id):
        """Check account status"""
        try:
            client = await self.get_client(account_id)
            await client.get_me()
            self.accounts_col.update_one(
                {'_id': ObjectId(account_id)},
                {'$set': {'status': AccountStatus.ACTIVE.value, 'updated_at': datetime.utcnow()}}
            )
            return True
        except Exception as e:
            logger.error(f"Error checking account: {e}")
            self.accounts_col.update_one(
                {'_id': ObjectId(account_id)},
                {'$set': {'status': AccountStatus.INACTIVE.value, 'updated_at': datetime.utcnow()}}
            )
            return False
    
    def get_active_accounts(self):
        """Get active accounts"""
        docs = self.accounts_col.find({'status': AccountStatus.ACTIVE.value})
        return [Account.from_dict(doc) for doc in docs]
    
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
    """任务管理器 - 管理所有私信任务的执行"""
    
    def __init__(self, db, account_manager, bot_application=None):
        self.db = db
        self.tasks_col = db[Task.COLLECTION_NAME]
        self.targets_col = db[Target.COLLECTION_NAME]
        self.logs_col = db[MessageLog.COLLECTION_NAME]
        self.account_manager = account_manager
        self.running_tasks = {}
        self.stop_flags = {}
        self.bot_application = bot_application  # 用于发送完成报告
    
    def create_task(self, name, message_text, message_format, media_type=MediaType.TEXT,
                   media_path=None, send_method=SendMethod.DIRECT, postbot_code=None, 
                   channel_link=None, min_interval=30, max_interval=120):
        """Create new task"""
        task = Task(
            name=name,
            message_text=message_text,
            message_format=message_format.value if isinstance(message_format, enum.Enum) else message_format,
            media_type=media_type.value if isinstance(media_type, enum.Enum) else media_type,
            media_path=media_path,
            send_method=send_method.value if isinstance(send_method, enum.Enum) else send_method,
            postbot_code=postbot_code,
            channel_link=channel_link,
            min_interval=min_interval,
            max_interval=max_interval,
            status=TaskStatus.PENDING.value
        )
        result = self.tasks_col.insert_one(task.to_dict())
        task._id = result.inserted_id
        return task
    
    def add_targets(self, task_id, target_list):
        """Add targets to task"""
        task_doc = self.tasks_col.find_one({'_id': ObjectId(task_id)})
        if not task_doc:
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
                target = Target(task_id=str(task_id), user_id=target_str)
            else:
                target = Target(task_id=str(task_id), username=target_str)
            self.targets_col.insert_one(target.to_dict())
            added_count += 1
        
        self.tasks_col.update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'total_targets': added_count, 'updated_at': datetime.utcnow()}}
        )
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
        task_doc = self.tasks_col.find_one({'_id': ObjectId(task_id)})
        if not task_doc:
            raise ValueError(f"Task {task_id} not found")
        
        task = Task.from_dict(task_doc)
        if task.status == TaskStatus.RUNNING.value:
            raise ValueError("Task already running")
        
        self.tasks_col.update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {
                'status': TaskStatus.RUNNING.value,
                'started_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }}
        )
        
        self.stop_flags[str(task_id)] = False
        asyncio_task = asyncio.create_task(self._execute_task(str(task_id)))
        self.running_tasks[str(task_id)] = asyncio_task
        return asyncio_task
    
    async def stop_task(self, task_id):
        """Stop task"""
        task_id_str = str(task_id)
        if task_id_str not in self.running_tasks:
            raise ValueError("Task not running")
        
        self.stop_flags[task_id_str] = True
        asyncio_task = self.running_tasks[task_id_str]
        try:
            await asyncio.wait_for(asyncio_task, timeout=10.0)
        except asyncio.TimeoutError:
            asyncio_task.cancel()
        
        self.tasks_col.update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'status': TaskStatus.PAUSED.value, 'updated_at': datetime.utcnow()}}
        )
        
        del self.running_tasks[task_id_str]
        del self.stop_flags[task_id_str]
    
    def delete_task(self, task_id):
        """Delete task and all associated data"""
        task_id_str = str(task_id)
        
        # Check if task is running
        if task_id_str in self.running_tasks:
            raise ValueError("Cannot delete a running task. Please stop it first.")
        
        # Delete associated targets
        self.targets_col.delete_many({'task_id': task_id_str})
        
        # Delete associated message logs
        self.logs_col.delete_many({'task_id': task_id_str})
        
        # Delete the task itself
        result = self.tasks_col.delete_one({'_id': ObjectId(task_id)})
        
        if result.deleted_count == 0:
            raise ValueError(f"Task {task_id} not found")
        
        logger.info(f"Task {task_id} and all associated data deleted successfully")
        return True
    
    async def _execute_task(self, task_id):
        """执行任务 - 支持多线程并发发送"""
        task_doc = self.tasks_col.find_one({'_id': ObjectId(task_id)})
        task = Task.from_dict(task_doc)
        
        logger.info("=" * 80)
        logger.info("开始执行任务")
        logger.info(f"任务ID: {task_id}")
        logger.info(f"任务名称: {task.name}")
        logger.info(f"发送方式: {task.send_method}")
        logger.info(f"线程数配置: {task.thread_count}")
        logger.info("=" * 80)
        
        # 启动进度监控任务
        progress_task = asyncio.create_task(self._monitor_progress(task_id))
        logger.info("进度监控任务已启动")
        
        try:
            # 获取待发送目标
            target_docs = self.targets_col.find({
                'task_id': task_id,
                'is_sent': False,
                'is_valid': True
            })
            targets = [Target.from_dict(doc) for doc in target_docs]
            
            logger.info(f"找到 {len(targets)} 个待发送目标")
            
            if not targets:
                logger.info("没有待发送目标，标记任务为已完成")
                self.tasks_col.update_one(
                    {'_id': ObjectId(task_id)},
                    {'$set': {
                        'status': TaskStatus.COMPLETED.value,
                        'completed_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow()
                    }}
                )
                # 自动生成并发送完成报告
                logger.info("开始生成完成报告...")
                await self._send_completion_reports(task_id)
                return
            
            # 获取活跃账户
            accounts = self.account_manager.get_active_accounts()
            logger.info(f"活跃账户数量: {len(accounts)}")
            
            if not accounts:
                # 检查是否有任何账户
                all_accounts_count = self.db[Account.COLLECTION_NAME].count_documents({})
                logger.error(f"没有活跃账户可用！总账户数: {all_accounts_count}")
                
                if all_accounts_count == 0:
                    error_msg = "No accounts found. Please add accounts first."
                    logger.error(f"Task {task_id}: {error_msg}")
                    raise ValueError("❌ 没有找到任何账户！\n\n请先在【账户管理】中添加账户。")
                else:
                    # 有账户但都不是 active 状态
                    inactive_accounts = self.db[Account.COLLECTION_NAME].count_documents({'status': {'$ne': AccountStatus.ACTIVE.value}})
                    error_msg = f"Found {all_accounts_count} accounts, but none are active. {inactive_accounts} accounts are inactive/banned/limited."
                    logger.error(f"Task {task_id}: {error_msg}")
                    
                    # 获取账户状态统计
                    status_stats = {}
                    for status in AccountStatus:
                        count = self.db[Account.COLLECTION_NAME].count_documents({'status': status.value})
                        if count > 0:
                            status_stats[status.value] = count
                    
                    stats_text = "\n".join([f"  • {status}: {count}" for status, count in status_stats.items()])
                    raise ValueError(f"❌ 没有可用的活跃账户！\n\n账户状态统计：\n{stats_text}\n\n请检查账户状态或添加新账户。")
            
            # 使用线程数配置确定并发执行
            thread_count = min(task.thread_count, len(accounts))
            logger.info("=" * 80)
            logger.info(f"并发执行配置:")
            logger.info(f"  配置的线程数: {task.thread_count}")
            logger.info(f"  实际使用线程数: {thread_count}")
            logger.info(f"  活跃账户数: {len(accounts)}")
            logger.info("=" * 80)
            
            # 将目标分批处理
            batch_size = max(1, len(targets) // thread_count)
            batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
            logger.info(f"目标分批: {len(batches)} 批，每批约 {batch_size} 个目标")
            
            # 为每个批次创建并发任务
            concurrent_tasks = []
            for batch_idx, batch in enumerate(batches[:thread_count]):
                account = accounts[batch_idx % len(accounts)]
                logger.info(f"批次 {batch_idx + 1}: 分配账户 {account.phone}，处理 {len(batch)} 个目标")
                concurrent_tasks.append(
                    self._process_batch(task_id, task, batch, account, batch_idx)
                )
            
            # 并发执行所有批次
            logger.info("=" * 80)
            logger.info(f"开始并发执行 {len(concurrent_tasks)} 个批次...")
            logger.info("=" * 80)
            await asyncio.gather(*concurrent_tasks, return_exceptions=True)
            
            # 获取最终任务状态
            task_doc = self.tasks_col.find_one({'_id': ObjectId(task_id)})
            task = Task.from_dict(task_doc)
            
            logger.info("=" * 80)
            logger.info("任务执行完成")
            logger.info(f"发送成功: {task.sent_count}")
            logger.info(f"发送失败: {task.failed_count}")
            logger.info(f"总计: {task.total_targets}")
            logger.info("=" * 80)
            
            # 更新任务状态为已完成
            self.tasks_col.update_one(
                {'_id': ObjectId(task_id)},
                {'$set': {
                    'status': TaskStatus.COMPLETED.value,
                    'completed_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }}
            )
            
            # 自动生成并发送完成报告
            logger.info("开始生成并发送完成报告...")
            await self._send_completion_reports(task_id)
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"任务执行出错: {task_id}")
            logger.error(f"错误信息: {str(e)}")
            logger.error("=" * 80)
            logger.error("详细错误堆栈:", exc_info=True)
            
            self.tasks_col.update_one(
                {'_id': ObjectId(task_id)},
                {'$set': {'status': TaskStatus.FAILED.value, 'updated_at': datetime.utcnow()}}
            )
        finally:
            # 取消进度监控
            logger.info("正在停止进度监控...")
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
            
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            if task_id in self.stop_flags:
                del self.stop_flags[task_id]
            logger.info(f"任务 {task_id}: 清理完成")
    
    async def _process_batch(self, task_id, task, targets, account, batch_idx):
        """处理一批目标 - 使用单个账户"""
        logger.info(f"[批次 {batch_idx}] 开始处理 {len(targets)} 个目标，使用账户: {account.phone}")
        
        for idx, target in enumerate(targets):
            # 检查停止标志
            if self.stop_flags.get(task_id, False):
                logger.info(f"[批次 {batch_idx}] 检测到停止标志，停止执行")
                break
            
            logger.info(f"[批次 {batch_idx}] 处理目标 {idx + 1}/{len(targets)}: {target.username or target.user_id}")
            
            # 检查每日限额
            account_doc = self.db[Account.COLLECTION_NAME].find_one({'_id': account._id})
            if account_doc:
                account = Account.from_dict(account_doc)
                if account.messages_sent_today >= account.daily_limit:
                    logger.warning(f"[批次 {batch_idx}] 账户 {account.phone} 达到每日限额，停止批次")
                    break
                
                # 重置每日计数器（如果需要）
                if account.last_used and account.last_used.date() < datetime.utcnow().date():
                    logger.info(f"[批次 {batch_idx}] 重置账户 {account.phone} 的每日计数器")
                    self.db[Account.COLLECTION_NAME].update_one(
                        {'_id': account._id},
                        {'$set': {'messages_sent_today': 0, 'updated_at': datetime.utcnow()}}
                    )
                    account.messages_sent_today = 0
            
            # 发送消息
            logger.info(f"[批次 {batch_idx}] 正在发送消息到目标: {target.username or target.user_id}")
            success = await self._send_message(task, target, account)
            
            if success:
                # 更新成功计数
                self.tasks_col.update_one(
                    {'_id': ObjectId(task_id)},
                    {'$inc': {'sent_count': 1}, '$set': {'updated_at': datetime.utcnow()}}
                )
                self.db[Account.COLLECTION_NAME].update_one(
                    {'_id': account._id},
                    {
                        '$inc': {'messages_sent_today': 1, 'total_messages_sent': 1},
                        '$set': {'last_used': datetime.utcnow(), 'updated_at': datetime.utcnow()}
                    }
                )
                logger.info(f"[批次 {batch_idx}] ✅ 发送成功: {target.username or target.user_id}")
            else:
                # 更新失败计数
                self.tasks_col.update_one(
                    {'_id': ObjectId(task_id)},
                    {'$inc': {'failed_count': 1}, '$set': {'updated_at': datetime.utcnow()}}
                )
                logger.warning(f"[批次 {batch_idx}] ❌ 发送失败: {target.username or target.user_id}")
            
            # 更新账户最后使用时间
            self.db[Account.COLLECTION_NAME].update_one(
                {'_id': account._id},
                {'$set': {'last_used': datetime.utcnow(), 'updated_at': datetime.utcnow()}}
            )
            
            # 消息间隔延迟
            delay = random.randint(task.min_interval, task.max_interval)
            logger.info(f"[批次 {batch_idx}] 等待 {delay} 秒后发送下一条消息...")
            await asyncio.sleep(delay)
        
        logger.info(f"[批次 {batch_idx}] 批次处理完成")
    
    async def _monitor_progress(self, task_id):
        """监控和更新任务进度 - 使用30-60秒随机间隔"""
        try:
            while True:
                # Use random interval between 30-60 seconds
                interval = random.randint(30, 60)
                await asyncio.sleep(interval)
                # 进度在 _process_batch 中自动更新
                # 这里只是保持监控任务活跃
                logger.debug(f"任务 {task_id}: 进度监控心跳 (下次检查间隔: {interval}秒)")
        except asyncio.CancelledError:
            logger.info(f"Task {task_id}: Progress monitor cancelled")
            raise
    
    async def _send_completion_reports(self, task_id):
        """生成并自动发送完成报告 - 任务完成后自动执行"""
        try:
            logger.info(f"========================================")
            logger.info(f"任务完成 - 开始生成报告")
            logger.info(f"任务ID: {task_id}")
            logger.info(f"========================================")
            
            results = self.export_task_results(task_id)
            if not results:
                logger.warning(f"任务 {task_id}: 无结果可导出")
                return
            
            # 生成时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.info(f"报告时间戳: {timestamp}")
            
            # 生成3个报告文件
            success_file = os.path.join(Config.RESULTS_DIR, f"发送成功的用户名_{task_id}_{timestamp}.txt")
            failed_file = os.path.join(Config.RESULTS_DIR, f"发送失败的用户名_{task_id}_{timestamp}.txt")
            log_file = os.path.join(Config.RESULTS_DIR, f"任务运行日志_{task_id}_{timestamp}.txt")
            
            # 写入成功用户列表
            logger.info(f"生成成功用户列表: {len(results['success_targets'])} 个用户")
            with open(success_file, 'w', encoding='utf-8') as f:
                f.write(f"任务完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"总成功数: {len(results['success_targets'])}\n")
                f.write("=" * 50 + "\n\n")
                for t in results['success_targets']:
                    f.write(f"{t.username or t.user_id}\n")
            
            # 写入失败用户列表
            logger.info(f"生成失败用户列表: {len(results['failed_targets'])} 个用户")
            with open(failed_file, 'w', encoding='utf-8') as f:
                f.write(f"任务完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"总失败数: {len(results['failed_targets'])}\n")
                f.write("=" * 50 + "\n\n")
                for t in results['failed_targets']:
                    f.write(f"{t.username or t.user_id}: {t.error_message or '未知错误'}\n")
            
            # 写入运行日志 - 详细版本
            logger.info(f"生成运行日志: {len(results['logs'])} 条记录")
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"任务运行日志\n")
                f.write(f"任务ID: {task_id}\n")
                f.write(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
                
                # 预先批量获取所有账户和目标信息（避免N+1查询）
                unique_account_ids = list(set([log.account_id for log in results['logs'] if log.account_id]))
                unique_target_ids = list(set([log.target_id for log in results['logs'] if log.target_id]))
                
                # 批量查询账户信息 - 安全转换ObjectId
                valid_account_ids = []
                for aid in unique_account_ids:
                    if aid and isinstance(aid, str) and len(aid) == 24:  # MongoDB ObjectId是24位十六进制字符串
                        try:
                            valid_account_ids.append(ObjectId(aid))
                        except Exception:
                            pass
                
                account_docs = self.db[Account.COLLECTION_NAME].find({
                    '_id': {'$in': valid_account_ids}
                })
                accounts_map = {str(doc['_id']): Account.from_dict(doc) for doc in account_docs}
                
                # 批量查询目标信息 - 安全转换ObjectId
                valid_target_ids = []
                for tid in unique_target_ids:
                    if tid and isinstance(tid, str) and len(tid) == 24:
                        try:
                            valid_target_ids.append(ObjectId(tid))
                        except Exception:
                            pass
                
                target_docs = self.targets_col.find({
                    '_id': {'$in': valid_target_ids}
                })
                targets_map = {str(doc['_id']): Target.from_dict(doc) for doc in target_docs}
                
                # 统计每个账户的发送情况
                account_stats = {}
                for log in results['logs']:
                    account_id = log.account_id
                    if account_id not in account_stats:
                        # 从预加载的账户信息中获取
                        account = accounts_map.get(account_id)
                        if account:
                            account_stats[account_id] = {
                                'phone': account.phone,
                                'success': 0,
                                'failed': 0,
                                'errors': {}
                            }
                        else:
                            account_stats[account_id] = {
                                'phone': 'Unknown',
                                'success': 0,
                                'failed': 0,
                                'errors': {}
                            }
                    
                    if log.success:
                        account_stats[account_id]['success'] += 1
                    else:
                        account_stats[account_id]['failed'] += 1
                        # 分类错误原因
                        error_type = self._categorize_error(log.error_message)
                        if error_type not in account_stats[account_id]['errors']:
                            account_stats[account_id]['errors'][error_type] = 0
                        account_stats[account_id]['errors'][error_type] += 1
                
                # 写入账户统计
                f.write("📊 账户统计:\n")
                f.write("-" * 50 + "\n")
                for account_id, stats in account_stats.items():
                    f.write(f"\n📱 账户: {stats['phone']}\n")
                    f.write(f"   ✅ 已成功发送: {stats['success']}条\n")
                    f.write(f"   ❌ 发送失败: {stats['failed']}条\n")
                    if stats['errors']:
                        f.write(f"   失败原因统计:\n")
                        for error_type, count in stats['errors'].items():
                            f.write(f"      • {error_type}: {count}次\n")
                f.write("\n" + "=" * 50 + "\n\n")
                
                # 写入详细日志
                f.write("📝 详细发送记录:\n")
                f.write("-" * 50 + "\n\n")
                for log in results['logs']:
                    # 从预加载的数据中获取账户信息
                    account_id = log.account_id
                    phone = account_stats.get(account_id, {}).get('phone', 'Unknown')
                    
                    # 从预加载的数据中获取目标用户信息
                    target = targets_map.get(log.target_id)
                    target_name = "Unknown"
                    if target:
                        target_name = target.username or target.user_id or "Unknown"
                    
                    status = "✅ 成功" if log.success else "❌ 失败"
                    
                    # 格式化消息内容预览（最多50个字符），处理None情况
                    message_text = log.message_text or ""
                    message_preview = (message_text[:50] + "...") if len(message_text) > 50 else message_text
                    
                    f.write(f"[{log.sent_at}]\n")
                    f.write(f"账户: {phone}\n")
                    f.write(f"目标: {target_name}\n")
                    f.write(f"状态: {status}\n")
                    
                    if log.success:
                        f.write(f"私信内容: {message_preview}\n")
                    else:
                        error_category = self._categorize_error(log.error_message)
                        f.write(f"失败原因: {error_category}\n")
                        f.write(f"详细错误: {log.error_message}\n")
                    
                    f.write("\n")
            
            # 如果有bot_application，自动发送报告给管理员
            if self.bot_application and Config.ADMIN_USER_ID:
                logger.info(f"========================================")
                logger.info(f"自动发送报告给管理员")
                logger.info(f"管理员ID: {Config.ADMIN_USER_ID}")
                logger.info(f"========================================")
                
                # 发送完成消息
                completion_text = (
                    f"🎉 <b>任务完成，用户名已用完！</b>\n\n"
                    f"📊 任务统计：\n"
                    f"✅ 发送成功: {len(results['success_targets'])}\n"
                    f"❌ 发送失败: {len(results['failed_targets'])}\n\n"
                    f"📁 正在发送日志报告..."
                )
                
                try:
                    await self.bot_application.bot.send_message(
                        chat_id=Config.ADMIN_USER_ID,
                        text=completion_text,
                        parse_mode='HTML'
                    )
                    logger.info("完成消息已发送")
                except Exception as e:
                    logger.error(f"发送完成消息失败: {e}")
                
                # 发送3个文件
                files_to_send = [
                    (success_file, "发送成功的用户名.txt"),
                    (failed_file, "发送失败的用户名.txt"),
                    (log_file, "任务运行日志.txt")
                ]
                
                for file_path, filename in files_to_send:
                    try:
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                            logger.info(f"发送文件: {filename}")
                            with open(file_path, 'rb') as f:
                                await self.bot_application.bot.send_document(
                                    chat_id=Config.ADMIN_USER_ID,
                                    document=f,
                                    filename=filename,
                                    caption=f"📄 {filename}"
                                )
                            logger.info(f"文件发送成功: {filename}")
                        else:
                            logger.warning(f"文件为空或不存在: {filename}")
                    except Exception as e:
                        logger.error(f"发送文件失败 {filename}: {e}")
                
                logger.info("========================================")
                logger.info("所有报告文件已发送完成")
                logger.info("========================================")
            else:
                logger.info("未配置bot_application或ADMIN_USER_ID，报告文件已生成但未自动发送")
            
        except Exception as e:
            logger.error(f"任务 {task_id}: 生成完成报告出错: {e}", exc_info=True)
    
    async def _send_message(self, task, target, account):
        """发送消息 - 支持所有发送方式"""
        try:
            # 获取账户的Telegram客户端
            logger.info(f"使用账户 {account.phone} 发送消息")
            client = await self.account_manager.get_client(str(account._id))
            
            # 确定接收者（用户ID或用户名）
            recipient = int(target.user_id) if target.user_id else target.username
            logger.info(f"目标接收者: {recipient}")
            
            # 获取目标用户实体
            try:
                logger.info(f"正在获取用户实体: {recipient}")
                entity = await client.get_entity(recipient)
                logger.info(f"用户实体获取成功")
            except Exception as e:
                logger.error(f"获取用户实体失败 {recipient}: {e}")
                self.targets_col.update_one(
                    {'_id': target._id},
                    {'$set': {'is_valid': False, 'error_message': str(e)}}
                )
                self._log_message(str(task._id), str(account._id), str(target._id), task.message_text, False, str(e))
                return False
            
            # 提取用户信息用于消息个性化
            user_info = MessageFormatter.extract_user_info(entity)
            logger.info(f"用户信息: {user_info.get('first_name', '')} {user_info.get('last_name', '')}")
            
            self.targets_col.update_one(
                {'_id': target._id},
                {'$set': {
                    'first_name': user_info.get('first_name', ''),
                    'last_name': user_info.get('last_name', '')
                }}
            )
            
            # 个性化消息内容
            personalized = MessageFormatter.personalize(task.message_text, user_info)
            parse_mode = MessageFormatter.get_parse_mode(task.message_format)
            sent_message = None
            
            # 根据不同的发送方式处理
            if task.send_method == SendMethod.POSTBOT.value:
                # Post代码发送 - 通过 @postbot 的内联模式
                logger.info(f"使用Post代码发送，代码: {task.postbot_code}")
                try:
                    # 获取 @postbot 实体
                    logger.info("正在连接 @postbot...")
                    postbot = await client.get_entity('postbot')
                    
                    # 使用内联查询获取 post 内容
                    logger.info(f"查询 @postbot 内联结果: {task.postbot_code}")
                    results = await client.inline_query(postbot, task.postbot_code)
                    
                    if not results:
                        logger.error("@postbot 内联查询无结果")
                        raise ValueError(f"Post代码 {task.postbot_code} 无效或已过期")
                    
                    # 发送第一个内联结果给目标用户
                    logger.info(f"找到 {len(results)} 个内联结果，发送第一个...")
                    sent_message = await results[0].click(entity)
                    logger.info("Post 内容发送成功")
                        
                except Exception as e:
                    logger.error(f"通过 @postbot 发送失败: {e}")
                    raise
            
            elif task.send_method in [SendMethod.CHANNEL_FORWARD.value, SendMethod.CHANNEL_FORWARD_HIDDEN.value]:
                # 频道转发
                logger.info(f"频道转发模式: {task.send_method}")
                logger.info(f"频道链接: {task.channel_link}")
                try:
                    # Parse channel link: https://t.me/channel_name/message_id
                    match = re.match(r'https://t\.me/([^/]+)/(\d+)', task.channel_link)
                    if not match:
                        raise ValueError(f"Invalid channel link format: {task.channel_link}")
                    
                    channel_username = match.group(1)
                    message_id = int(match.group(2))
                    
                    # Get channel entity
                    channel = await client.get_entity(channel_username)
                    # Get specific message
                    message = await client.get_messages(channel, ids=message_id)
                    
                    if not message:
                        raise ValueError(f"Message {message_id} not found in channel {channel_username}")
                    
                    # Forward message
                    if task.send_method == SendMethod.CHANNEL_FORWARD_HIDDEN.value:
                        # Forward without source
                        sent_message = await client.send_message(entity, message.message, file=message.media)
                    else:
                        # Forward with source
                        sent_message = await client.forward_messages(entity, message, channel)
                except Exception as e:
                    logger.error(f"Failed to forward from channel: {e}")
                    raise
            
            else:
                # 直接发送 (DIRECT method)
                if task.media_type == MediaType.TEXT.value:
                    sent_message = await client.send_message(entity, personalized, parse_mode=parse_mode)
                elif task.media_type in [MediaType.IMAGE.value, MediaType.VIDEO.value, MediaType.DOCUMENT.value]:
                    sent_message = await client.send_file(entity, task.media_path, caption=personalized, parse_mode=parse_mode)
                elif task.media_type == MediaType.VOICE.value:
                    sent_message = await client.send_file(entity, task.media_path, voice_note=True, caption=personalized, parse_mode=parse_mode)
            
            # Pin message if configured
            if task.pin_message and sent_message:
                try:
                    await client.pin_message(entity, sent_message)
                    logger.info(f"Message pinned for {recipient}")
                except Exception as e:
                    logger.warning(f"Failed to pin message for {recipient}: {e}")
            
            # Delete dialog if configured
            if task.delete_dialog:
                try:
                    await client.delete_dialog(entity)
                    logger.info(f"Dialog deleted for {recipient}")
                except Exception as e:
                    logger.warning(f"Failed to delete dialog for {recipient}: {e}")
            
            self.targets_col.update_one(
                {'_id': target._id},
                {'$set': {'is_sent': True, 'sent_at': datetime.utcnow()}}
            )
            
            self._log_message(str(task._id), str(account._id), str(target._id), personalized, True, None)
            logger.info(f"Message sent to {recipient}")
            return True
            
        except (UserPrivacyRestrictedError, UserIsBlockedError, ChatWriteForbiddenError, UserNotMutualContactError) as e:
            error_msg = f"Privacy error: {type(e).__name__}"
            self.targets_col.update_one(
                {'_id': target._id},
                {'$set': {'error_message': error_msg}}
            )
            self._log_message(str(task._id), str(account._id), str(target._id), task.message_text, False, error_msg)
            return False
            
        except FloodWaitError as e:
            error_msg = f"FloodWait: {e.seconds}s"
            self.db[Account.COLLECTION_NAME].update_one(
                {'_id': account._id},
                {'$set': {'status': AccountStatus.LIMITED.value, 'updated_at': datetime.utcnow()}}
            )
            self._log_message(str(task._id), str(account._id), str(target._id), task.message_text, False, error_msg)
            await asyncio.sleep(e.seconds)
            return False
            
        except PeerFloodError:
            error_msg = "PeerFlood"
            self.db[Account.COLLECTION_NAME].update_one(
                {'_id': account._id},
                {'$set': {'status': AccountStatus.LIMITED.value, 'updated_at': datetime.utcnow()}}
            )
            self._log_message(str(task._id), str(account._id), str(target._id), task.message_text, False, error_msg)
            return False
            
        except Exception as e:
            error_msg = str(e)
            self.targets_col.update_one(
                {'_id': target._id},
                {'$set': {'error_message': error_msg}}
            )
            self._log_message(str(task._id), str(account._id), str(target._id), task.message_text, False, error_msg)
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
        self.logs_col.insert_one(log.to_dict())
    
    def _categorize_error(self, error_message):
        """将错误消息分类为友好的中文描述"""
        if not error_message:
            return "未知错误"
        
        error_lower = error_message.lower()
        
        # 隐私和权限相关错误
        if 'privacy' in error_lower or 'userprivacyrestricted' in error_lower:
            return "账户隐私限制（对方设置了隐私保护）"
        if 'blocked' in error_lower or 'userisblocked' in error_lower:
            return "已被对方屏蔽"
        if 'chatwriteforbidden' in error_lower:
            return "无权限发送消息"
        if 'notmutualcontact' in error_lower or 'usernotmutualcontact' in error_lower:
            return "非双向联系人（需要互相添加好友）"
        
        # 限流相关错误
        if 'flood' in error_lower:
            if 'peerflood' in error_lower:
                return "账户已被限流（发送过多消息）"
            return "操作过于频繁，已被限流"
        
        # 账户状态相关
        if 'banned' in error_lower:
            return "账户已封禁"
        if 'restricted' in error_lower:
            return "账户已受限"
        if 'deactivated' in error_lower:
            return "账户已停用"
        
        # 用户不存在或无效
        if 'notfound' in error_lower or 'invalid' in error_lower:
            return "用户不存在或已失效"
        if 'deleted' in error_lower:
            return "用户已删除账号"
        
        # 网络和连接错误
        if 'timeout' in error_lower or 'connection' in error_lower:
            return "网络连接超时"
        if 'network' in error_lower:
            return "网络错误"
        
        # Postbot 相关错误
        if 'postbot' in error_lower:
            return "Post代码无效或已过期"
        
        # 其他 - 安全处理可能的None情况
        if error_message:
            error_preview = error_message[:50] if len(error_message) > 50 else error_message
            return f"其他错误：{error_preview}"
        return "未知错误"
    
    def get_task_progress(self, task_id):
        """Get task progress"""
        task_doc = self.tasks_col.find_one({'_id': ObjectId(task_id)})
        if not task_doc:
            return None
        
        task = Task.from_dict(task_doc)
        return {
            'task_id': str(task._id),
            'name': task.name,
            'status': task.status,
            'total_targets': task.total_targets,
            'sent_count': task.sent_count,
            'failed_count': task.failed_count,
            'pending_count': task.total_targets - task.sent_count - task.failed_count,
            'progress_percent': (task.sent_count / task.total_targets * 100) if task.total_targets > 0 else 0
        }
    
    def export_task_results(self, task_id):
        """Export results"""
        task_doc = self.tasks_col.find_one({'_id': ObjectId(task_id)})
        if not task_doc:
            return None
        
        success_docs = self.targets_col.find({'task_id': task_id, 'is_sent': True})
        success_targets = [Target.from_dict(doc) for doc in success_docs]
        
        failed_docs = self.targets_col.find({
            'task_id': task_id,
            'is_sent': False,
            'error_message': {'$ne': None}
        })
        failed_targets = [Target.from_dict(doc) for doc in failed_docs]
        
        log_docs = self.logs_col.find({'task_id': task_id})
        logs = [MessageLog.from_dict(doc) for doc in log_docs]
        
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
 MESSAGE_INPUT, FORMAT_SELECT, SEND_METHOD_SELECT, MEDIA_SELECT, MEDIA_UPLOAD,
 TARGET_INPUT, TASK_NAME_INPUT, SESSION_UPLOAD, TDATA_UPLOAD, POSTBOT_CODE_INPUT,
 CHANNEL_LINK_INPUT, PREVIEW_CONFIG,
 CONFIG_THREAD_INPUT, CONFIG_INTERVAL_MIN_INPUT, CONFIG_BIDIRECT_INPUT) = range(18)

# Global managers
account_manager = None
task_manager = None
db = None


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
        account_id = data.split('_')[2]
        logger.info(f"User {user_id} checking account {account_id}")
        await check_account(query, account_id)
    
    # Tasks
    elif data == 'tasks_list':
        logger.info(f"User {user_id} viewing tasks list")
        await list_tasks(query)
    # Note: tasks_create is handled by ConversationHandler
    elif data.startswith('task_detail_'):
        task_id = data.split('_')[2]
        logger.info(f"User {user_id} viewing task {task_id} detail")
        await show_task_detail(query, task_id)
    elif data.startswith('task_config_'):
        task_id = data.split('_')[2]
        logger.info(f"User {user_id} configuring task {task_id}")
        await show_task_config(query, task_id)
    elif data.startswith('cfg_toggle_'):
        # Handle toggle buttons for pin_message, delete_dialog, repeat_send
        parts = data.split('_')
        toggle_type = parts[2]  # pin, delete, repeat
        task_id = parts[3]
        await toggle_task_config(query, task_id, toggle_type)
    elif data == 'noop':
        # No operation for info-only buttons
        await query.answer()
    elif data.startswith('task_start_'):
        task_id = data.split('_')[2]
        logger.info(f"User {user_id} starting task {task_id}")
        await start_task_handler(query, task_id)
    elif data.startswith('task_stop_'):
        task_id = data.split('_')[2]
        logger.info(f"User {user_id} stopping task {task_id}")
        await stop_task_handler(query, task_id)
    elif data.startswith('task_progress_'):
        # Handle both task_progress_refresh_ and task_progress_
        if 'refresh' in data:
            task_id = data.split('_')[3]
            logger.info(f"User {user_id} refreshing task {task_id} progress")
            await refresh_task_progress(query, task_id)
        else:
            task_id = data.split('_')[2]
            logger.info(f"User {user_id} viewing task {task_id} progress")
            await show_task_progress(query, task_id)
    elif data.startswith('task_export_'):
        task_id = data.split('_')[2]
        logger.info(f"User {user_id} exporting task {task_id} results")
        await export_results(query, task_id)
    elif data.startswith('task_delete_'):
        task_id = data.split('_')[2]
        logger.info(f"User {user_id} deleting task {task_id}")
        await delete_task_handler(query, task_id)
    
    # Format selection
    elif data.startswith('format_'):
        format_name = data.split('_')[1]
        context.user_data['message_format'] = MessageFormat[format_name.upper()]
        logger.info(f"User {user_id} selected format: {format_name}")
        # After format selection, go to media type selection
        return await select_media_type(query)
    
    # Send method selection
    elif data.startswith('sendmethod_'):
        if data == 'sendmethod_preview':
            return await show_preview(query, context)
        elif data == 'sendmethod_direct':
            context.user_data['send_method'] = SendMethod.DIRECT
            logger.info(f"User {user_id} selected send method: direct")
            # For direct send, request message input
            await query.message.reply_text(
                "📤 <b>直接发送</b>\n\n"
                "请输入消息内容：\n\n"
                "💡 可使用变量：{name}, {first_name}, {last_name}, {full_name}, {username}",
                parse_mode='HTML'
            )
            return MESSAGE_INPUT
        elif data == 'sendmethod_postbot':
            context.user_data['send_method'] = SendMethod.POSTBOT
            logger.info(f"User {user_id} selected send method: postbot")
            return await request_postbot_code(query)
        elif data == 'sendmethod_channel_forward':
            context.user_data['send_method'] = SendMethod.CHANNEL_FORWARD
            logger.info(f"User {user_id} selected send method: channel_forward")
            return await request_channel_link(query)
        elif data == 'sendmethod_channel_forward_hidden':
            context.user_data['send_method'] = SendMethod.CHANNEL_FORWARD_HIDDEN
            logger.info(f"User {user_id} selected send method: channel_forward_hidden")
            return await request_channel_link(query)
    
    # Preview continue
    elif data == 'preview_continue':
        # After preview, always go to target list
        return await request_target_list(query)
    
    # Preview back - allow user to modify configuration
    elif data == 'preview_back':
        send_method = context.user_data.get('send_method', SendMethod.DIRECT)
        logger.info(f"User {user_id} going back from preview, send_method: {send_method.value}")
        
        if send_method == SendMethod.DIRECT:
            # For direct send, go back to message input
            await query.message.reply_text(
                "📤 <b>直接发送</b>\n\n"
                "请重新输入消息内容：\n\n"
                "💡 可使用变量：{name}, {first_name}, {last_name}, {full_name}, {username}",
                parse_mode='HTML'
            )
            return MESSAGE_INPUT
        elif send_method == SendMethod.POSTBOT:
            # For postbot, go back to code input
            return await request_postbot_code(query)
        elif send_method in [SendMethod.CHANNEL_FORWARD, SendMethod.CHANNEL_FORWARD_HIDDEN]:
            # For channel forward, go back to link input
            return await request_channel_link(query)
    
    # Media selection
    elif data.startswith('media_'):
        media_name = data.split('_')[1]
        context.user_data['media_type'] = MediaType[media_name.upper()]
        logger.info(f"User {user_id} selected media type: {media_name}")
        if context.user_data['media_type'] == MediaType.TEXT:
            # Show preview before going to target list
            return await show_preview(query, context)
        else:
            return await request_media_upload(query)
    
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
    account_docs = db[Account.COLLECTION_NAME].find()
    accounts = [Account.from_dict(doc) for doc in account_docs]
    
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
            status_emoji = {'active': '✅', 'banned': '🚫', 'limited': '⚠️', 'inactive': '❌'}.get(account.status, '❓')
            text += (
                f"{status_emoji} <b>{account.phone}</b>\n"
                f"   状态: {account.status}\n"
                f"   今日: {account.messages_sent_today}/{account.daily_limit}\n\n"
            )
            keyboard.append([InlineKeyboardButton(f"检查 {account.phone}", callback_data=f'account_check_{str(account._id)}')])
        
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
    task_docs = db[Task.COLLECTION_NAME].find()
    tasks = [Task.from_dict(doc) for doc in task_docs]
    
    if not tasks:
        text = "📝 <b>任务列表</b>\n\n暂无任务"
        keyboard = [
            [InlineKeyboardButton("➕ 创建新任务", callback_data='tasks_create')],
            [InlineKeyboardButton("🔙 返回", callback_data='menu_tasks')]
        ]
    else:
        text = f"📝 <b>任务列表</b>\n\n共 {len(tasks)} 个任务：\n\n"
        keyboard = []
        
        # Show tasks in a 2-column grid
        row = []
        for idx, task in enumerate(tasks):
            status_emoji = {'pending': '⏳', 'running': '▶️', 'paused': '⏸️', 'completed': '✅', 'failed': '❌'}.get(task.status, '❓')
            button_text = f"{status_emoji} {task.name}"
            row.append(InlineKeyboardButton(button_text, callback_data=f'task_detail_{str(task._id)}'))
            
            # Create a new row after every 2 tasks
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        # Add remaining task if odd number
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("➕ 创建新任务", callback_data='tasks_create')])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data='menu_tasks')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def show_task_detail(query, task_id):
    """Show task detail with configuration options and real-time progress"""
    task_doc = db[Task.COLLECTION_NAME].find_one({'_id': ObjectId(task_id)})
    if not task_doc:
        await query.answer("❌ 任务不存在", show_alert=True)
        return
    
    task = Task.from_dict(task_doc)
    status_emoji = {'pending': '⏳', 'running': '▶️', 'paused': '⏸️', 'completed': '✅', 'failed': '❌'}.get(task.status, '❓')
    progress = (task.sent_count / task.total_targets * 100) if task.total_targets > 0 else 0
    
    # Build progress display for running tasks
    if task.status == TaskStatus.RUNNING.value:
        text = (
            f"⬇ <b>正在私信中</b> ⬇\n"
            f"进度 {task.sent_count}/{task.total_targets} ({progress:.1f}%)\n\n"
            f"👥 总用户数    {task.total_targets}\n"
            f"✅ 发送成功    {task.sent_count}\n"
            f"❌ 发送失败    {task.failed_count}\n\n"
        )
        
        # Calculate estimated time
        if task.total_targets and task.sent_count is not None and task.failed_count is not None:
            remaining = task.total_targets - task.sent_count - task.failed_count
            if remaining > 0 and task.min_interval and task.max_interval:
                avg_interval = (task.min_interval + task.max_interval) / 2
                estimated_seconds = remaining * avg_interval
                estimated_time = timedelta(seconds=int(estimated_seconds))
                text += f"⏱️ 预计剩余时间: {estimated_time}\n"
        
        if task.started_at:
            elapsed = datetime.utcnow() - task.started_at
            text += f"⏰ 已运行时间: {elapsed}\n"
    else:
        text = (
            f"{status_emoji} <b>{task.name}</b>\n\n"
            f"📊 进度: {task.sent_count}/{task.total_targets} ({progress:.1f}%)\n"
            f"✅ 成功: {task.sent_count}\n"
            f"❌ 失败: {task.failed_count}\n\n"
            f"<b>⚙️ 当前配置:</b>\n"
            f"🧵 多账号线程数: {task.thread_count}\n"
            f"⏱️ 发送间隔: {task.min_interval}-{task.max_interval}秒\n"
            f"🔄 无视双向次数: {task.ignore_bidirectional_limit}\n"
            f"📌 置顶消息: {'✔️' if task.pin_message else '❌'}\n"
            f"🗑️ 删除对话框: {'✔️' if task.delete_dialog else '❌'}\n"
            f"🔁 重复发送: {'✔️' if task.repeat_send else '❌'}\n"
        )
        
        if task.started_at:
            elapsed = datetime.utcnow() - task.started_at
            text += f"\n⏰ 已运行时间: {elapsed}\n"
    
    keyboard = []
    
    # Configuration buttons (only if not running)
    if task.status != TaskStatus.RUNNING.value:
        keyboard.append([
            InlineKeyboardButton("⚙️ 参数配置", callback_data=f'task_config_{task_id}'),
            InlineKeyboardButton("🗑️ 删除任务", callback_data=f'task_delete_{task_id}')
        ])
    
    # Start/Stop buttons
    if task.status in [TaskStatus.PENDING.value, TaskStatus.PAUSED.value]:
        keyboard.append([InlineKeyboardButton("▶️ 开始私信", callback_data=f'task_start_{task_id}')])
    elif task.status == TaskStatus.RUNNING.value:
        keyboard.append([
            InlineKeyboardButton("🔄 刷新进度", callback_data=f'task_detail_{task_id}'),
            InlineKeyboardButton("⏸️ 停止任务", callback_data=f'task_stop_{task_id}')
        ])
    
    # Export button for completed tasks
    if task.status == TaskStatus.COMPLETED.value:
        keyboard.append([InlineKeyboardButton("📥 导出结果", callback_data=f'task_export_{task_id}')])
    
    keyboard.append([InlineKeyboardButton("🔙 返回任务列表", callback_data='tasks_list')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def show_task_config(query, task_id):
    """Show task configuration options"""
    task_doc = db[Task.COLLECTION_NAME].find_one({'_id': ObjectId(task_id)})
    if not task_doc:
        await query.answer("❌ 任务不存在", show_alert=True)
        return
    
    task = Task.from_dict(task_doc)
    
    text = (
        f"⚙️ <b>配置 - {task.name}</b>\n\n"
        f"当前配置如下，点击按钮进行调整："
    )
    
    keyboard = [
        [
            InlineKeyboardButton(f"🧵 线程数: {task.thread_count}", callback_data=f'cfg_thread_{task_id}'),
            InlineKeyboardButton(f"⏱️ 间隔: {task.min_interval}-{task.max_interval}s", callback_data=f'cfg_interval_{task_id}')
        ],
        [InlineKeyboardButton(f"🔄 无视双向: {task.ignore_bidirectional_limit}次", callback_data=f'cfg_bidirect_{task_id}')],
        [
            InlineKeyboardButton(f"{'✔️' if task.pin_message else '❌'} 置顶消息", callback_data=f'cfg_toggle_pin_{task_id}'),
            InlineKeyboardButton(f"{'✔️' if task.delete_dialog else '❌'} 删除对话", callback_data=f'cfg_toggle_delete_{task_id}')
        ],
        [InlineKeyboardButton(f"{'✔️' if task.repeat_send else '❌'} 重复发送", callback_data=f'cfg_toggle_repeat_{task_id}')],
        [InlineKeyboardButton("✅ 配置完成", callback_data=f'task_detail_{task_id}')],
        [InlineKeyboardButton("🔙 返回", callback_data=f'task_detail_{task_id}')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def request_thread_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request thread count configuration"""
    query = update.callback_query
    await query.answer()
    task_id = query.data.split('_')[2]
    context.user_data['config_task_id'] = task_id
    prompt_msg = await query.message.reply_text(
        "🧵 <b>配置线程数</b>\n\n"
        "请输入要使用的账号数量（线程数）：\n\n"
        "💡 建议：1-10\n"
        "⚠️ 线程数越多，发送速度越快，但风险也越高",
        parse_mode='HTML'
    )
    # Store prompt message ID for later deletion
    context.user_data['config_prompt_msg_id'] = prompt_msg.message_id
    return CONFIG_THREAD_INPUT


async def request_interval_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request interval configuration"""
    query = update.callback_query
    await query.answer()
    task_id = query.data.split('_')[2]
    context.user_data['config_task_id'] = task_id
    prompt_msg = await query.message.reply_text(
        "⏱️ <b>配置发送间隔</b>\n\n"
        "请输入最小间隔和最大间隔（秒），用空格分隔：\n\n"
        "💡 格式：最小值 最大值\n"
        "💡 例如：30 120\n"
        "⚠️ 间隔越短，风险越高",
        parse_mode='HTML'
    )
    # Store prompt message ID for later deletion
    context.user_data['config_prompt_msg_id'] = prompt_msg.message_id
    return CONFIG_INTERVAL_MIN_INPUT


async def request_bidirect_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request bidirectional limit configuration"""
    query = update.callback_query
    await query.answer()
    task_id = query.data.split('_')[2]
    context.user_data['config_task_id'] = task_id
    prompt_msg = await query.message.reply_text(
        "🔄 <b>配置无视双向次数</b>\n\n"
        "请输入无视双向联系人限制的次数：\n\n"
        "💡 0 = 不忽略限制\n"
        "💡 1-999 = 忽略次数\n"
        "⚠️ 设置过高可能导致封号",
        parse_mode='HTML'
    )
    # Store prompt message ID for later deletion
    context.user_data['config_prompt_msg_id'] = prompt_msg.message_id
    return CONFIG_BIDIRECT_INPUT


async def start_create_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Start task creation - Conversation entry point.
    
    Handles the tasks_create callback, prompts the user to input a task name,
    and transitions to TASK_NAME_INPUT state.
    
    Returns:
        int: TASK_NAME_INPUT state constant
    """
    query = update.callback_query
    await query.answer()
    logger.info(f"User {query.from_user.id} starting task creation")
    await query.message.reply_text("➕ <b>创建新任务</b>\n\n请输入任务名称：", parse_mode='HTML')
    context.user_data['creating_task'] = True
    return TASK_NAME_INPUT


async def handle_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task name"""
    context.user_data['task_name'] = update.message.text
    
    # Now go directly to send method selection
    keyboard = [
        [InlineKeyboardButton("📤 直接发送", callback_data='sendmethod_direct')],
        [InlineKeyboardButton("🤖 Post代码", callback_data='sendmethod_postbot')],
        [InlineKeyboardButton("📢 频道转发", callback_data='sendmethod_channel_forward')],
        [InlineKeyboardButton("🔒 隐藏转发来源", callback_data='sendmethod_channel_forward_hidden')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ 任务名称: <b>{update.message.text}</b>\n\n"
        "📮 <b>请选择发送方式配置：</b>\n\n"
        "📤 <b>直接发送</b> - 请配置文本消息（可以纯文字，也可以直接发图片带文字）\n"
        "🤖 <b>Post代码</b> - 使用 @postbot 配置的图文按钮\n"
        "📢 <b>频道转发</b> - 转发频道帖子\n"
        "🔒 <b>隐藏转发来源</b> - 转发频道帖子但隐藏来源",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    return SEND_METHOD_SELECT


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


async def handle_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media file upload"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} uploading media file")
    
    try:
        if not update.message.document and not update.message.photo and not update.message.video:
            await update.message.reply_text("❌ 请上传有效的媒体文件")
            return MEDIA_UPLOAD
        
        # Save the file
        if update.message.document:
            file = await update.message.document.get_file()
            file_ext = os.path.splitext(update.message.document.file_name)[1]
        elif update.message.photo:
            file = await update.message.photo[-1].get_file()
            file_ext = '.jpg'
        elif update.message.video:
            file = await update.message.video.get_file()
            file_ext = '.mp4'
        else:
            await update.message.reply_text("❌ 不支持的媒体类型")
            return MEDIA_UPLOAD
        
        # Save to media directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"media_{user_id}_{timestamp}{file_ext}"
        media_path = os.path.join(Config.MEDIA_DIR, filename)
        await file.download_to_drive(media_path)
        
        context.user_data['media_path'] = media_path
        logger.info(f"User {user_id} uploaded media to {media_path}")
        
        await update.message.reply_text("✅ 媒体文件已保存")
        
        # Show preview before going to target list
        return await show_preview_from_update(update, context)
        
    except Exception as e:
        logger.error(f"Error handling media upload for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 上传失败：{str(e)}")
        return MEDIA_UPLOAD


async def request_postbot_code(query):
    """Request postbot code input"""
    await query.message.reply_text(
        "🤖 <b>Post代码输入</b>\n\n"
        "请输入从 @postbot 获取的代码：\n\n"
        "💡 提示：使用 @postbot 创建图文按钮后，复制生成的代码粘贴到这里",
        parse_mode='HTML'
    )
    return POSTBOT_CODE_INPUT


async def handle_postbot_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle postbot code input with validation"""
    code = update.message.text.strip()
    
    # Validate postbot code format (must be like 693af80c53cb2)
    # Pattern: alphanumeric characters, minimum length defined by constant
    if not re.match(rf'^[a-zA-Z0-9]{{{POSTBOT_CODE_MIN_LENGTH},}}$', code):
        await update.message.reply_text(
            "❌ <b>代码格式错误</b>\n\n"
            "Post代码格式应该类似：<code>693af80c53cb2</code>\n\n"
            "请重新输入正确的代码：",
            parse_mode='HTML'
        )
        return POSTBOT_CODE_INPUT
    
    context.user_data['postbot_code'] = code
    context.user_data['message_text'] = f"使用 @postbot 代码: {code}"
    context.user_data['message_format'] = MessageFormat.PLAIN
    context.user_data['media_type'] = MediaType.TEXT
    
    await update.message.reply_text("✅ Post代码已保存")
    
    # Show preview before going to target list
    return await show_preview_from_update(update, context)


async def request_channel_link(query):
    """Request channel link input"""
    await query.message.reply_text(
        "📢 <b>频道链接输入</b>\n\n"
        "请输入频道帖子链接：\n\n"
        "💡 格式：https://t.me/channel_name/message_id",
        parse_mode='HTML'
    )
    return CHANNEL_LINK_INPUT


async def handle_channel_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle channel link input"""
    link = update.message.text.strip()
    context.user_data['channel_link'] = link
    
    # Set default values for channel forward
    send_method = context.user_data.get('send_method', SendMethod.CHANNEL_FORWARD)
    if send_method == SendMethod.CHANNEL_FORWARD_HIDDEN:
        context.user_data['message_text'] = f"转发频道帖子（隐藏来源）: {link}"
    else:
        context.user_data['message_text'] = f"转发频道帖子: {link}"
    
    context.user_data['message_format'] = MessageFormat.PLAIN
    context.user_data['media_type'] = MediaType.FORWARD
    
    await update.message.reply_text("✅ 频道链接已保存")
    
    # Show preview before going to target list
    return await show_preview_from_update(update, context)


async def show_preview(query, context):
    """Show preview of configured message"""
    message_text = context.user_data.get('message_text', '')
    message_format = context.user_data.get('message_format', MessageFormat.PLAIN)
    send_method = context.user_data.get('send_method', SendMethod.DIRECT)
    media_type = context.user_data.get('media_type', MediaType.TEXT)
    
    preview_text = (
        "👁️ <b>预览配置的广告文案！</b>\n\n"
        f"📮 发送方式：{SEND_METHOD_LABELS.get(send_method, send_method.value)}\n"
        f"📝 消息格式：{message_format.value}\n"
        f"📦 媒体类型：{MEDIA_TYPE_LABELS.get(media_type, media_type.value)}\n\n"
        f"<b>消息内容：</b>\n{message_text[:200]}{'...' if len(message_text) > 200 else ''}\n\n"
        f"======下一步===\n"
        f"✅ 配置完成"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ 配置完成", callback_data='preview_continue')],
        [InlineKeyboardButton("🔙 返回修改", callback_data='preview_back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(preview_text, parse_mode='HTML', reply_markup=reply_markup)
    return PREVIEW_CONFIG


async def show_preview_from_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show preview from update message (helper for text input handlers)"""
    message_text = context.user_data.get('message_text', '')
    message_format = context.user_data.get('message_format', MessageFormat.PLAIN)
    send_method = context.user_data.get('send_method', SendMethod.DIRECT)
    media_type = context.user_data.get('media_type', MediaType.TEXT)
    
    preview_text = (
        "👁️ <b>预览配置的广告文案！</b>\n\n"
        f"📮 发送方式：{SEND_METHOD_LABELS.get(send_method, send_method.value)}\n"
        f"📝 消息格式：{message_format.value}\n"
        f"📦 媒体类型：{MEDIA_TYPE_LABELS.get(media_type, media_type.value)}\n\n"
        f"<b>消息内容：</b>\n{message_text[:200]}{'...' if len(message_text) > 200 else ''}\n\n"
        f"======下一步===\n"
        f"✅ 配置完成"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ 配置完成", callback_data='preview_continue')],
        [InlineKeyboardButton("🔙 返回修改", callback_data='preview_back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(preview_text, parse_mode='HTML', reply_markup=reply_markup)
    return PREVIEW_CONFIG


async def request_target_list_from_update(update: Update):
    """Request target list from update (helper for text input handlers)"""
    await update.message.reply_text(
        "✅ 配置完成\n\n"
        "请发送目标列表：\n"
        "1️⃣ 直接发送（每行一个）\n"
        "2️⃣ 上传 .txt 文件\n\n"
        "格式：@username 或 用户ID"
    )
    return TARGET_INPUT


async def request_target_list(query):
    """Request target list"""
    await query.message.reply_text(
        "✅ <b>配置完成</b>\n\n"
        "<b>请发送目标列表：</b>\n"
        "1️⃣ 直接发送（每行一个）\n"
        "2️⃣ 上传 .txt 文件\n\n"
        "格式：@username（不带@也行）或 用户ID",
        parse_mode='HTML'
    )
    return TARGET_INPUT


async def handle_target_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle target input"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} submitting target input")
    
    try:
        if update.message.text:
            logger.info(f"User {user_id} sent text input")
            targets = update.message.text.strip().split('\n')
            logger.info(f"Parsed {len(targets)} targets from text")
        elif update.message.document:
            logger.info(f"User {user_id} sent document: {update.message.document.file_name}")
            file = await update.message.document.get_file()
            content = await file.download_as_bytearray()
            logger.info(f"Downloaded file: {len(content)} bytes")
            targets = task_manager.parse_target_file(bytes(content))
            logger.info(f"Parsed {len(targets)} targets from file")
        else:
            logger.warning(f"User {user_id} sent invalid input (no text or document)")
            await update.message.reply_text("❌ 无效输入\n\n请发送文本或上传 .txt 文件")
            return TARGET_INPUT
        
        if not targets:
            logger.warning(f"User {user_id} submitted empty target list")
            await update.message.reply_text("❌ 目标列表为空\n\n请添加至少一个目标")
            return TARGET_INPUT
        
        # Count original targets before deduplication
        original_count = len(targets)
        
        logger.info(f"Creating task for user {user_id}")
        task = task_manager.create_task(
            name=context.user_data['task_name'],
            message_text=context.user_data['message_text'],
            message_format=context.user_data['message_format'],
            media_type=context.user_data.get('media_type', MediaType.TEXT),
            media_path=context.user_data.get('media_path'),
            send_method=context.user_data.get('send_method', SendMethod.DIRECT),
            postbot_code=context.user_data.get('postbot_code'),
            channel_link=context.user_data.get('channel_link'),
            min_interval=Config.DEFAULT_MIN_INTERVAL,
            max_interval=Config.DEFAULT_MAX_INTERVAL
        )
        
        logger.info(f"Adding {len(targets)} targets to task {task._id}")
        added = task_manager.add_targets(task._id, targets)
        logger.info(f"Successfully added {added} targets to task {task._id}")
        
        # Calculate deduplication stats
        duplicates = original_count - added
        
        await update.message.reply_text(
            f"✅ <b>任务创建成功！</b>\n\n"
            f"📝 任务名称: {task.name}\n"
            f"📊 已收到 {original_count} 个用户\n"
            f"🔄 已去重 {duplicates} 个用户\n"
            f"✅ 最终添加 {added} 个用户\n\n"
            f"<b>注意：</b>用户名发一个自动删除一个，用完代表任务结束\n\n"
            f"前往任务列表开始任务\n\n"
            f"使用 /start 查看任务列表",
            parse_mode='HTML'
        )
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error handling target input for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ <b>处理失败</b>\n\n"
            f"错误：{str(e)}\n\n"
            f"请重试或使用 /start 返回主菜单",
            parse_mode='HTML'
        )
        return TARGET_INPUT


async def handle_thread_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle thread count configuration"""
    try:
        thread_count = int(update.message.text.strip())
        if thread_count < 1 or thread_count > 50:
            await update.message.reply_text("❌ 线程数必须在 1-50 之间，请重新输入：")
            return CONFIG_THREAD_INPUT
        
        task_id = context.user_data.get('config_task_id')
        db[Task.COLLECTION_NAME].update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'thread_count': thread_count, 'updated_at': datetime.utcnow()}}
        )
        
        msg = await update.message.reply_text(f"✅ 线程数已设置为：{thread_count}")
        # Auto-delete after configured delay
        await asyncio.sleep(CONFIG_MESSAGE_DELETE_DELAY)
        try:
            # Delete confirmation message
            await msg.delete()
            # Delete user input message
            await update.message.delete()
            # Delete prompt message
            prompt_msg_id = context.user_data.get('config_prompt_msg_id')
            if prompt_msg_id:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=prompt_msg_id
                )
        except Exception as e:
            logger.warning(f"Failed to delete config message: {e}")
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的数字：")
        return CONFIG_THREAD_INPUT


async def handle_interval_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interval configuration"""
    try:
        parts = update.message.text.strip().split()
        if len(parts) != 2:
            await update.message.reply_text("❌ 格式错误，请输入两个数字（用空格分隔）：")
            return CONFIG_INTERVAL_MIN_INPUT
        
        min_interval = int(parts[0])
        max_interval = int(parts[1])
        
        if min_interval < 1 or max_interval < min_interval or max_interval > 3600:
            await update.message.reply_text("❌ 间隔设置不合理，请重新输入：\n最小值 ≥ 1，最大值 ≥ 最小值，最大值 ≤ 3600")
            return CONFIG_INTERVAL_MIN_INPUT
        
        task_id = context.user_data.get('config_task_id')
        db[Task.COLLECTION_NAME].update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {
                'min_interval': min_interval,
                'max_interval': max_interval,
                'updated_at': datetime.utcnow()
            }}
        )
        
        msg = await update.message.reply_text(f"✅ 发送间隔已设置为：{min_interval}-{max_interval} 秒")
        # Auto-delete after configured delay
        await asyncio.sleep(CONFIG_MESSAGE_DELETE_DELAY)
        try:
            # Delete confirmation message
            await msg.delete()
            # Delete user input message
            await update.message.delete()
            # Delete prompt message
            prompt_msg_id = context.user_data.get('config_prompt_msg_id')
            if prompt_msg_id:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=prompt_msg_id
                )
        except Exception as e:
            logger.warning(f"Failed to delete config message: {e}")
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的数字：")
        return CONFIG_INTERVAL_MIN_INPUT


async def handle_bidirect_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bidirectional limit configuration"""
    try:
        limit = int(update.message.text.strip())
        if limit < 0 or limit > 999:
            await update.message.reply_text("❌ 次数必须在 0-999 之间，请重新输入：")
            return CONFIG_BIDIRECT_INPUT
        
        task_id = context.user_data.get('config_task_id')
        db[Task.COLLECTION_NAME].update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'ignore_bidirectional_limit': limit, 'updated_at': datetime.utcnow()}}
        )
        
        msg = await update.message.reply_text(f"✅ 无视双向次数已设置为：{limit}")
        # Auto-delete after configured delay
        await asyncio.sleep(CONFIG_MESSAGE_DELETE_DELAY)
        try:
            # Delete confirmation message
            await msg.delete()
            # Delete user input message
            await update.message.delete()
            # Delete prompt message
            prompt_msg_id = context.user_data.get('config_prompt_msg_id')
            if prompt_msg_id:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=prompt_msg_id
                )
        except Exception as e:
            logger.warning(f"Failed to delete config message: {e}")
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的数字：")
        return CONFIG_BIDIRECT_INPUT


async def start_task_handler(query, task_id):
    """Start task and show progress in new message"""
    try:
        await task_manager.start_task(task_id)
        await query.answer("✅ 任务已开始")
        
        # Send a NEW message for progress tracking instead of editing the existing one
        task_doc = db[Task.COLLECTION_NAME].find_one({'_id': ObjectId(task_id)})
        task = Task.from_dict(task_doc)
        
        # Create initial progress message with inline buttons
        text = (
            f"⬇ <b>正在私信中</b> ⬇\n"
            f"进度 0/{task.total_targets} (0.0%)\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("👥 总用户数", callback_data='noop'),
                InlineKeyboardButton(f"{task.total_targets}", callback_data='noop')
            ],
            [
                InlineKeyboardButton("✅ 发送成功", callback_data='noop'),
                InlineKeyboardButton("0", callback_data='noop')
            ],
            [
                InlineKeyboardButton("❌ 发送失败", callback_data='noop'),
                InlineKeyboardButton("0", callback_data='noop')
            ],
            [
                InlineKeyboardButton("🔄 刷新进度", callback_data=f'task_progress_refresh_{task_id}'),
                InlineKeyboardButton("⏸️ 停止任务", callback_data=f'task_stop_{task_id}')
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        progress_msg = await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        
        # Wait 1 second then refresh to show initial progress
        await asyncio.sleep(1)
        
        # Get updated task data
        task_doc = db[Task.COLLECTION_NAME].find_one({'_id': ObjectId(task_id)})
        if task_doc:
            task = Task.from_dict(task_doc)
            progress = (task.sent_count / task.total_targets * 100) if task.total_targets > 0 else 0
            
            text = (
                f"⬇ <b>正在私信中</b> ⬇\n"
                f"进度 {task.sent_count}/{task.total_targets} ({progress:.1f}%)\n"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("👥 总用户数", callback_data='noop'),
                    InlineKeyboardButton(f"{task.total_targets}", callback_data='noop')
                ],
                [
                    InlineKeyboardButton("✅ 发送成功", callback_data='noop'),
                    InlineKeyboardButton(f"{task.sent_count}", callback_data='noop')
                ],
                [
                    InlineKeyboardButton("❌ 发送失败", callback_data='noop'),
                    InlineKeyboardButton(f"{task.failed_count}", callback_data='noop')
                ],
                [
                    InlineKeyboardButton("🔄 刷新进度", callback_data=f'task_progress_refresh_{task_id}'),
                    InlineKeyboardButton("⏸️ 停止任务", callback_data=f'task_stop_{task_id}')
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await progress_msg.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
            except Exception as e:
                logger.warning(f"Failed to update initial progress: {e}")
        
    except ValueError as e:
        # ValueError 通常包含用户友好的错误消息
        await query.message.reply_text(str(e), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Unexpected error starting task {task_id}: {e}", exc_info=True)
        await query.answer(f"❌ 启动失败: {str(e)}", show_alert=True)


async def stop_task_handler(query, task_id):
    """Stop task immediately"""
    try:
        # Set stop flag immediately
        task_manager.stop_flags[task_id] = True
        
        # Update task status immediately
        db[Task.COLLECTION_NAME].update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'status': TaskStatus.PAUSED.value, 'updated_at': datetime.utcnow()}}
        )
        
        await query.answer("⏸️ 任务停止中...")
        
        # Try to stop the task gracefully
        if task_id in task_manager.running_tasks:
            asyncio_task = task_manager.running_tasks[task_id]
            try:
                await asyncio.wait_for(asyncio_task, timeout=TASK_STOP_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                # Cancel forcefully if it takes too long
                asyncio_task.cancel()
            
            if task_id in task_manager.running_tasks:
                del task_manager.running_tasks[task_id]
        
        # Show updated task detail
        await show_task_detail(query, task_id)
        
    except Exception as e:
        logger.error(f"Error stopping task {task_id}: {e}", exc_info=True)
        await query.answer(f"❌ 停止失败: {str(e)}", show_alert=True)


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


async def refresh_task_progress(query, task_id):
    """刷新任务进度 - 更新进度显示的内联按钮"""
    logger.info(f"刷新任务进度: Task ID={task_id}")
    
    task_doc = db[Task.COLLECTION_NAME].find_one({'_id': ObjectId(task_id)})
    if not task_doc:
        await query.answer("❌ 任务不存在", show_alert=True)
        return
    
    task = Task.from_dict(task_doc)
    progress = (task.sent_count / task.total_targets * 100) if task.total_targets > 0 else 0
    
    logger.info(f"任务进度: {task.sent_count}/{task.total_targets} ({progress:.1f}%)")
    
    # 构建进度文本
    text = (
        f"⬇ <b>正在私信中</b> ⬇\n"
        f"进度 {task.sent_count}/{task.total_targets} ({progress:.1f}%)\n"
    )
    
    # 添加预计剩余时间
    if task.status == TaskStatus.RUNNING.value:
        if task.total_targets and task.sent_count is not None and task.failed_count is not None:
            remaining = task.total_targets - task.sent_count - task.failed_count
            if remaining > 0 and task.min_interval and task.max_interval:
                avg_interval = (task.min_interval + task.max_interval) / 2
                estimated_seconds = remaining * avg_interval
                estimated_time = timedelta(seconds=int(estimated_seconds))
                text += f"\n⏱️ 预计剩余: {estimated_time}"
        
        if task.started_at:
            elapsed = datetime.utcnow() - task.started_at
            text += f"\n⏰ 已运行: {elapsed}"
    
    # 创建内联按钮 - 左侧标签，右侧数值
    keyboard = [
        [
            InlineKeyboardButton("👥 总用户数", callback_data='noop'),
            InlineKeyboardButton(f"{task.total_targets}", callback_data='noop')
        ],
        [
            InlineKeyboardButton("✅ 发送成功", callback_data='noop'),
            InlineKeyboardButton(f"{task.sent_count}", callback_data='noop')
        ],
        [
            InlineKeyboardButton("❌ 发送失败", callback_data='noop'),
            InlineKeyboardButton(f"{task.failed_count}", callback_data='noop')
        ],
        [
            InlineKeyboardButton("🔄 刷新进度", callback_data=f'task_progress_refresh_{task_id}'),
            InlineKeyboardButton("⏸️ 停止任务", callback_data=f'task_stop_{task_id}')
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        await query.answer("✅ 进度已刷新")
    except Exception as e:
        logger.error(f"更新进度显示失败: {e}")
        await query.answer("刷新完成")


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
    
    # Only send non-empty files (Telegram API rejects empty files)
    try:
        if os.path.getsize(success_file) > 0:
            with open(success_file, 'rb') as f:
                await query.message.reply_document(document=f, filename="success.txt")
    except Exception as e:
        logger.warning(f"Failed to send success file: {e}")
    
    try:
        if os.path.getsize(failed_file) > 0:
            with open(failed_file, 'rb') as f:
                await query.message.reply_document(document=f, filename="failed.txt")
    except Exception as e:
        logger.warning(f"Failed to send failed file: {e}")
    
    try:
        if os.path.getsize(log_file) > 0:
            with open(log_file, 'rb') as f:
                await query.message.reply_document(document=f, filename="log.txt")
    except Exception as e:
        logger.warning(f"Failed to send log file: {e}")
    
    await query.message.reply_text("✅ 结果已导出")


async def toggle_task_config(query, task_id, toggle_type):
    """Toggle task configuration options"""
    task_doc = db[Task.COLLECTION_NAME].find_one({'_id': ObjectId(task_id)})
    if not task_doc:
        await query.answer("❌ 任务不存在", show_alert=True)
        return
    
    task = Task.from_dict(task_doc)
    
    # Toggle the appropriate field
    if toggle_type == 'pin':
        task.pin_message = not task.pin_message
        db[Task.COLLECTION_NAME].update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'pin_message': task.pin_message, 'updated_at': datetime.utcnow()}}
        )
        await query.answer(f"{'✔️ 已启用' if task.pin_message else '❌ 已禁用'} 置顶消息")
    elif toggle_type == 'delete':
        task.delete_dialog = not task.delete_dialog
        db[Task.COLLECTION_NAME].update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'delete_dialog': task.delete_dialog, 'updated_at': datetime.utcnow()}}
        )
        await query.answer(f"{'✔️ 已启用' if task.delete_dialog else '❌ 已禁用'} 删除对话框")
    elif toggle_type == 'repeat':
        task.repeat_send = not task.repeat_send
        db[Task.COLLECTION_NAME].update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'repeat_send': task.repeat_send, 'updated_at': datetime.utcnow()}}
        )
        await query.answer(f"{'✔️ 已启用' if task.repeat_send else '❌ 已禁用'} 重复发送")
    
    # Refresh the config page
    await show_task_config(query, task_id)


async def delete_task_handler(query, task_id):
    """Delete task handler"""
    try:
        # Get task info before deleting
        task_doc = db[Task.COLLECTION_NAME].find_one({'_id': ObjectId(task_id)})
        if not task_doc:
            await query.answer("❌ 任务不存在", show_alert=True)
            return
        
        task = Task.from_dict(task_doc)
        
        # Delete the task
        task_manager.delete_task(task_id)
        
        await query.answer(f"✅ 任务 '{task.name}' 已删除", show_alert=True)
        
        # Refresh the task list
        await list_tasks(query)
        
    except ValueError as e:
        logger.error(f"Error deleting task {task_id}: {e}")
        await query.answer(f"❌ {str(e)}", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error deleting task {task_id}: {e}")
        await query.answer("❌ 删除任务时发生错误", show_alert=True)


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
    total_accounts = db[Account.COLLECTION_NAME].count_documents({})
    active_accounts = db[Account.COLLECTION_NAME].count_documents({'status': AccountStatus.ACTIVE.value})
    total_tasks = db[Task.COLLECTION_NAME].count_documents({})
    completed_tasks = db[Task.COLLECTION_NAME].count_documents({'status': TaskStatus.COMPLETED.value})
    total_msgs = db[MessageLog.COLLECTION_NAME].count_documents({})
    success_msgs = db[MessageLog.COLLECTION_NAME].count_documents({'success': True})
    
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
    global account_manager, task_manager, db
    
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
    
    logger.info(f"Initializing database: {Config.MONGODB_URI}")
    db = init_db(Config.MONGODB_URI, Config.MONGODB_DATABASE)
    logger.info("Database initialized successfully")
    
    logger.info("Initializing account manager...")
    account_manager = AccountManager(db)
    logger.info("Account manager initialized")
    
    logger.info("Initializing task manager...")
    # 先创建application以便传递给TaskManager
    logger.info("Building bot application...")
    application = Application.builder().token(Config.BOT_TOKEN).build()
    
    # 创建task_manager时传入bot_application
    task_manager = TaskManager(db, account_manager, application)
    logger.info("Task manager initialized with bot application")
    
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
            SEND_METHOD_SELECT: [CallbackQueryHandler(button_handler)],
            POSTBOT_CODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_postbot_code_input)],
            CHANNEL_LINK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_link_input)],
            PREVIEW_CONFIG: [CallbackQueryHandler(button_handler)],
            MEDIA_SELECT: [CallbackQueryHandler(button_handler)],
            MEDIA_UPLOAD: [MessageHandler((filters.Document.ALL | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND, handle_media_upload)],
            TARGET_INPUT: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, handle_target_input)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    application.add_handler(task_conv)
    
    # Task configuration conversation handler
    logger.info("Registering task configuration conversation handler...")
    config_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(request_thread_config, pattern='^cfg_thread_'),
            CallbackQueryHandler(request_interval_config, pattern='^cfg_interval_'),
            CallbackQueryHandler(request_bidirect_config, pattern='^cfg_bidirect_')
        ],
        states={
            CONFIG_THREAD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_thread_config)],
            CONFIG_INTERVAL_MIN_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_interval_config)],
            CONFIG_BIDIRECT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bidirect_config)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    application.add_handler(config_conv)
    
    # General button handler (registered AFTER conversation handlers)
    logger.info("Registering general button handler...")
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("=" * 80)
    logger.info("Bot started successfully! Listening for updates...")
    logger.info("=" * 80)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
