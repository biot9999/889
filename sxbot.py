#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 私信机器人管理系统
用于管理多个 Telegram 账户并执行批量私信任务
使用内联按钮进行交互，无需使用命令
"""

import os
import sys
import asyncio
import logging
import random
import json
import tempfile
import zipfile
import base64
import struct
import ipaddress
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

# 第三方库导入
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, 
        CallbackQueryHandler, 
        CommandHandler,
        MessageHandler,
        ContextTypes,
        ConversationHandler,
        filters
    )
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON, create_engine
    from sqlalchemy.orm import relationship, declarative_base, sessionmaker, Session
    from cryptography.fernet import Fernet
    from dotenv import load_dotenv
except ImportError as e:
    print(f"缺少依赖库: {e}")
    print("请运行: pip install python-telegram-bot telethon sqlalchemy cryptography python-dotenv")
    sys.exit(1)

# 加载环境变量
load_dotenv()

# ==================== 配置部分 ====================

# 机器人配置
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
API_ID = os.getenv('API_ID', '')
API_HASH = os.getenv('API_HASH', '')

# 数据库配置
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///telegram_bot.db')

# 安全配置
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
ALLOWED_USERS = [int(uid.strip()) for uid in os.getenv('ALLOWED_USERS', '').split(',') if uid.strip()]

# 发送限制配置
MAX_MESSAGES_PER_ACCOUNT_PER_DAY = int(os.getenv('MAX_MESSAGES_PER_ACCOUNT_PER_DAY', '50'))
MIN_DELAY_SECONDS = int(os.getenv('MIN_DELAY_SECONDS', '30'))
MAX_DELAY_SECONDS = int(os.getenv('MAX_DELAY_SECONDS', '120'))

# 日志配置
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ==================== 会话状态常量 ====================
# 用于 ConversationHandler 的状态
(
    WAITING_SESSION_STRING,
    WAITING_PHONE_NUMBER,
    WAITING_VERIFICATION_CODE,
    WAITING_MESSAGE_TEMPLATE,
    WAITING_TARGET_LIST,
    WAITING_ACCOUNT_SELECTION,
    WAITING_DELAY_CONFIG,
    WAITING_LIMIT_CONFIG,
) = range(8)

# ==================== 数据库模型 ====================

Base = declarative_base()


class User(Base):
    """用户表 - 存储机器人用户信息"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    accounts = relationship('Account', back_populates='user', cascade='all, delete-orphan')
    tasks = relationship('Task', back_populates='user', cascade='all, delete-orphan')


class Account(Base):
    """账户表 - 存储用于发送消息的 Telegram 账户"""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    session_string = Column(Text, nullable=False)  # 加密存储
    phone_number = Column(String(20))
    status = Column(String(20), default='active')  # active, banned, limited
    messages_sent_today = Column(Integer, default=0)
    last_used_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship('User', back_populates='accounts')
    send_logs = relationship('SendLog', back_populates='account', cascade='all, delete-orphan')


class Task(Base):
    """任务表 - 存储私信发送任务"""
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_template = Column(Text, nullable=False)
    target_list = Column(JSON)  # 目标用户列表
    account_ids = Column(JSON)  # 使用的账户ID列表
    status = Column(String(20), default='pending')  # pending, running, completed, failed, stopped
    config = Column(JSON)  # 配置信息（包含媒体类型、格式等）
    progress = Column(JSON)  # 进度信息
    media_type = Column(String(20), default='text')  # text, photo, video, voice, document
    media_url = Column(Text)  # 媒体文件URL或路径
    parse_mode = Column(String(20), default='Markdown')  # None, Markdown, HTML
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    user = relationship('User', back_populates='tasks')
    send_logs = relationship('SendLog', back_populates='task', cascade='all, delete-orphan')


class SendLog(Base):
    """发送日志表 - 记录每条消息的发送情况"""
    __tablename__ = 'send_logs'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    target_user = Column(String(100), nullable=False)
    success = Column(Boolean, default=False)
    error_message = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    task = relationship('Task', back_populates='send_logs')
    account = relationship('Account', back_populates='send_logs')


# ==================== 数据库管理器 ====================

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()
    
    def get_or_create_user(self, telegram_id: int, username: str = None) -> User:
        """获取或创建用户"""
        session = self.get_session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                user = User(telegram_id=telegram_id, username=username)
                session.add(user)
                session.commit()
                session.refresh(user)
            return user
        finally:
            session.close()


# ==================== 加密工具 ====================

class Encryptor:
    """加密器 - 用于加密和解密敏感信息"""
    
    def __init__(self, key: str):
        self.fernet = Fernet(key.encode())
    
    def encrypt(self, data: str) -> str:
        """加密字符串"""
        return self.fernet.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """解密字符串"""
        return self.fernet.decrypt(encrypted_data.encode()).decode()


# ==================== 账户管理器 ====================

class AccountManager:
    """账户管理器 - 管理 Telegram 账户"""
    
    def __init__(self, db: DatabaseManager, encryptor: Encryptor):
        self.db = db
        self.encryptor = encryptor
    
    def add_account(self, user_id: int, session_string: str, phone_number: str = None) -> Account:
        """添加新账户"""
        session = self.db.get_session()
        try:
            encrypted_session = self.encryptor.encrypt(session_string)
            account = Account(
                user_id=user_id,
                session_string=encrypted_session,
                phone_number=phone_number,
                status='active'
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            logger.info(f"添加账户成功: {phone_number}")
            return account
        finally:
            session.close()
    
    def get_user_accounts(self, user_id: int) -> List[Account]:
        """获取用户的所有账户"""
        session = self.db.get_session()
        try:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user:
                return session.query(Account).filter_by(user_id=user.id).all()
            return []
        finally:
            session.close()
    
    def get_account(self, account_id: int) -> Optional[Account]:
        """获取账户"""
        session = self.db.get_session()
        try:
            return session.query(Account).filter_by(id=account_id).first()
        finally:
            session.close()
    
    def update_account_status(self, account_id: int, status: str):
        """更新账户状态"""
        session = self.db.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if account:
                account.status = status
                session.commit()
                logger.info(f"账户 {account_id} 状态更新为: {status}")
        finally:
            session.close()
    
    async def verify_account(self, session_string: str) -> bool:
        """验证账户是否有效"""
        try:
            decrypted_session = self.encryptor.decrypt(session_string) if session_string.startswith('gA') else session_string
            client = TelegramClient(StringSession(decrypted_session), API_ID, API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                await client.disconnect()
                return True
            await client.disconnect()
            return False
        except Exception as e:
            logger.error(f"账户验证失败: {e}")
            return False


# ==================== 任务管理器 ====================

class TaskManager:
    """任务管理器 - 管理私信发送任务"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.running_tasks: Dict[int, bool] = {}  # task_id -> is_running
    
    def create_task(
        self,
        user_id: int,
        message_template: str,
        target_list: List[str],
        account_ids: List[int],
        config: Dict[str, Any],
        media_type: str = 'text',
        media_url: str = None,
        parse_mode: str = 'Markdown'
    ) -> Task:
        """创建新任务"""
        session = self.db.get_session()
        try:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            task = Task(
                user_id=user.id,
                message_template=message_template,
                target_list=target_list,
                account_ids=account_ids,
                status='pending',
                config=config,
                progress={'total': len(target_list), 'sent': 0, 'failed': 0},
                media_type=media_type,
                media_url=media_url,
                parse_mode=parse_mode
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            logger.info(f"创建任务成功: Task ID {task.id}")
            return task
        finally:
            session.close()
    
    def get_user_tasks(self, user_id: int) -> List[Task]:
        """获取用户的所有任务"""
        session = self.db.get_session()
        try:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user:
                return session.query(Task).filter_by(user_id=user.id).order_by(Task.created_at.desc()).all()
            return []
        finally:
            session.close()
    
    def get_task(self, task_id: int) -> Optional[Task]:
        """获取任务"""
        session = self.db.get_session()
        try:
            return session.query(Task).filter_by(id=task_id).first()
        finally:
            session.close()
    
    def update_task_status(self, task_id: int, status: str):
        """更新任务状态"""
        session = self.db.get_session()
        try:
            task = session.query(Task).filter_by(id=task_id).first()
            if task:
                task.status = status
                if status == 'running':
                    task.started_at = datetime.utcnow()
                elif status in ['completed', 'failed', 'stopped']:
                    task.completed_at = datetime.utcnow()
                session.commit()
        finally:
            session.close()
    
    def update_task_progress(self, task_id: int, sent: int, failed: int):
        """更新任务进度"""
        session = self.db.get_session()
        try:
            task = session.query(Task).filter_by(id=task_id).first()
            if task:
                progress = task.progress or {}
                progress['sent'] = sent
                progress['failed'] = failed
                task.progress = progress
                session.commit()
        finally:
            session.close()
    
    def stop_task(self, task_id: int):
        """停止任务"""
        self.running_tasks[task_id] = False
        self.update_task_status(task_id, 'stopped')
        logger.info(f"任务 {task_id} 已停止")


# ==================== 消息发送器 ====================

class MessageSender:
    """消息发送器 - 执行批量私信发送"""
    
    def __init__(
        self,
        db: DatabaseManager,
        encryptor: Encryptor,
        account_manager: AccountManager,
        task_manager: TaskManager
    ):
        self.db = db
        self.encryptor = encryptor
        self.account_manager = account_manager
        self.task_manager = task_manager
    
    async def send_task(self, task_id: int):
        """执行发送任务"""
        task = self.task_manager.get_task(task_id)
        if not task:
            logger.error(f"任务不存在: {task_id}")
            return
        
        # 标记任务为运行中
        self.task_manager.update_task_status(task_id, 'running')
        self.task_manager.running_tasks[task_id] = True
        
        config = task.config or {}
        min_delay = config.get('min_delay', MIN_DELAY_SECONDS)
        max_delay = config.get('max_delay', MAX_DELAY_SECONDS)
        max_per_account = config.get('max_per_account', MAX_MESSAGES_PER_ACCOUNT_PER_DAY)
        
        target_list = task.target_list
        account_ids = task.account_ids
        
        sent_count = 0
        failed_count = 0
        
        # 为每个目标分配账户（轮询方式）
        account_index = 0
        
        for target in target_list:
            # 检查任务是否被停止
            if not self.task_manager.running_tasks.get(task_id, False):
                logger.info(f"任务 {task_id} 已被停止")
                break
            
            # 选择账户
            if not account_ids:
                logger.error("没有可用的账户")
                break
            
            account_id = account_ids[account_index % len(account_ids)]
            account = self.account_manager.get_account(account_id)
            
            if not account or account.status != 'active':
                account_index += 1
                continue
            
            # 检查账户今日发送限制
            if account.messages_sent_today >= max_per_account:
                logger.warning(f"账户 {account_id} 已达到今日发送限制")
                account_index += 1
                continue
            
            # 发送消息 - 传递媒体类型和解析模式
            success = await self._send_message(
                account, 
                target, 
                task.message_template, 
                task_id,
                media_type=task.media_type or 'text',
                media_url=task.media_url,
                parse_mode=task.parse_mode
            )
            
            if success:
                sent_count += 1
                # 更新账户发送计数
                self._update_account_sent_count(account_id)
            else:
                failed_count += 1
            
            # 更新任务进度
            self.task_manager.update_task_progress(task_id, sent_count, failed_count)
            
            # 随机延迟
            delay = random.randint(min_delay, max_delay)
            logger.info(f"等待 {delay} 秒后发送下一条消息...")
            await asyncio.sleep(delay)
            
            account_index += 1
        
        # 任务完成
        self.task_manager.update_task_status(task_id, 'completed')
        self.task_manager.running_tasks[task_id] = False
        logger.info(f"任务 {task_id} 完成: 成功 {sent_count}, 失败 {failed_count}")
    
    async def _send_message(self, account: Account, target: str, message_template: str, task_id: int, media_type: str = 'text', media_url: str = None, parse_mode: str = None) -> bool:
        """
        发送单条消息 - 支持富媒体和个性化
        
        Args:
            account: 发送账户
            target: 目标用户
            message_template: 消息模板
            task_id: 任务ID
            media_type: 媒体类型 (text, photo, video, voice, document)
            media_url: 媒体文件URL或路径
            parse_mode: 解析模式 (Markdown, HTML, None)
        """
        client = None
        try:
            # 解密 session string
            decrypted_session = self.encryptor.decrypt(account.session_string)
            
            # 创建 Telethon 客户端
            client = TelegramClient(StringSession(decrypted_session), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"账户 {account.id} 未授权")
                self.account_manager.update_account_status(account.id, 'limited')
                await client.disconnect()
                return False
            
            # 获取目标用户信息（用于个性化）
            try:
                target_entity = await client.get_entity(target)
                first_name = getattr(target_entity, 'first_name', '')
                last_name = getattr(target_entity, 'last_name', '')
                username = getattr(target_entity, 'username', '')
                
                # 个性化变量替换 - 参考 TeleRaptor 的个性化功能
                message = message_template
                message = message.replace('{name}', username or first_name)
                message = message.replace('{first_name}', first_name)
                message = message.replace('{last_name}', last_name)
                message = message.replace('{full_name}', f"{first_name} {last_name}".strip())
                message = message.replace('{username}', f"@{username}" if username else first_name)
                
            except Exception as e:
                logger.warning(f"无法获取用户信息 {target}: {e}")
                message = message_template
            
            # 根据媒体类型发送 - 参考 TeleRaptor 的富媒体支持
            if media_type == 'photo' and media_url:
                # 发送图片消息
                await client.send_file(
                    target,
                    media_url,
                    caption=message,
                    parse_mode=parse_mode
                )
            elif media_type == 'video' and media_url:
                # 发送视频消息
                await client.send_file(
                    target,
                    media_url,
                    caption=message,
                    parse_mode=parse_mode
                )
            elif media_type == 'voice' and media_url:
                # 发送语音消息
                await client.send_file(
                    target,
                    media_url,
                    voice_note=True
                )
            elif media_type == 'document' and media_url:
                # 发送文档
                await client.send_file(
                    target,
                    media_url,
                    caption=message,
                    parse_mode=parse_mode
                )
            else:
                # 发送纯文本消息 - 支持 Markdown/HTML 格式
                if parse_mode == 'Markdown':
                    await client.send_message(target, message, parse_mode='md')
                elif parse_mode == 'HTML':
                    await client.send_message(target, message, parse_mode='html')
                else:
                    await client.send_message(target, message)
            
            # 记录发送日志
            self._log_send(task_id, account.id, target, True, None)
            
            # 更新账户最后使用时间
            self._update_account_last_used(account.id)
            
            await client.disconnect()
            logger.info(f"消息发送成功: {target} (类型: {media_type})")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"消息发送失败 ({target}): {error_msg}")
            
            # 记录发送日志
            self._log_send(task_id, account.id, target, False, error_msg)
            
            # 检查是否是账户被封禁
            if 'banned' in error_msg.lower() or 'flood' in error_msg.lower():
                self.account_manager.update_account_status(account.id, 'banned')
            
            if client:
                await client.disconnect()
            
            return False
    
    def _log_send(self, task_id: int, account_id: int, target: str, success: bool, error: str = None):
        """记录发送日志"""
        session = self.db.get_session()
        try:
            log = SendLog(
                task_id=task_id,
                account_id=account_id,
                target_user=target,
                success=success,
                error_message=error
            )
            session.add(log)
            session.commit()
        finally:
            session.close()
    
    def _update_account_sent_count(self, account_id: int):
        """更新账户发送计数"""
        session = self.db.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if account:
                account.messages_sent_today = (account.messages_sent_today or 0) + 1
                session.commit()
        finally:
            session.close()
    
    def _update_account_last_used(self, account_id: int):
        """更新账户最后使用时间"""
        session = self.db.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if account:
                account.last_used_at = datetime.utcnow()
                session.commit()
        finally:
            session.close()


# ==================== 内联键盘布局 ====================

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """获取主菜单键盘"""
    keyboard = [
        [InlineKeyboardButton("📱 账户管理", callback_data="menu_accounts")],
        [InlineKeyboardButton("📝 任务管理", callback_data="menu_tasks")],
        [InlineKeyboardButton("⚙️ 全局设置", callback_data="menu_settings")],
        [InlineKeyboardButton("❓ 帮助文档", callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_accounts_menu_keyboard() -> InlineKeyboardMarkup:
    """获取账户管理菜单键盘"""
    keyboard = [
        [InlineKeyboardButton("➕ 添加账户", callback_data="account_add")],
        [InlineKeyboardButton("📋 账户列表", callback_data="account_list")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_account_add_method_keyboard() -> InlineKeyboardMarkup:
    """获取账户添加方式选择键盘"""
    keyboard = [
        [InlineKeyboardButton("🔑 Session String", callback_data="account_add_session")],
        [InlineKeyboardButton("📄 Session JSON 文件", callback_data="account_add_json")],
        [InlineKeyboardButton("📁 TData 文件夹", callback_data="account_add_tdata")],
        [InlineKeyboardButton("📞 手机号+验证码", callback_data="account_add_phone")],
        [InlineKeyboardButton("🔙 返回", callback_data="menu_accounts")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_tasks_menu_keyboard() -> InlineKeyboardMarkup:
    """获取任务管理菜单键盘"""
    keyboard = [
        [InlineKeyboardButton("➕ 创建新任务", callback_data="task_new")],
        [InlineKeyboardButton("📋 任务列表", callback_data="task_list")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_keyboard(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    """获取返回键盘"""
    keyboard = [[InlineKeyboardButton("🔙 返回", callback_data=callback_data)]]
    return InlineKeyboardMarkup(keyboard)


def get_task_action_keyboard(task_id: int, status: str) -> InlineKeyboardMarkup:
    """获取任务操作键盘"""
    keyboard = []
    if status == 'pending':
        keyboard.append([InlineKeyboardButton("▶️ 开始执行", callback_data=f"task_start_{task_id}")])
    elif status == 'running':
        keyboard.append([InlineKeyboardButton("⏸️ 停止任务", callback_data=f"task_stop_{task_id}")])
    
    keyboard.append([InlineKeyboardButton("📊 查看详情", callback_data=f"task_detail_{task_id}")])
    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="task_list")])
    return InlineKeyboardMarkup(keyboard)


def get_media_type_keyboard() -> InlineKeyboardMarkup:
    """获取媒体类型选择键盘 - TeleRaptor 风格的富媒体支持"""
    keyboard = [
        [InlineKeyboardButton("📝 纯文本", callback_data="media_text")],
        [InlineKeyboardButton("🖼️ 图片消息", callback_data="media_photo")],
        [InlineKeyboardButton("🎥 视频消息", callback_data="media_video")],
        [InlineKeyboardButton("🎤 语音消息", callback_data="media_voice")],
        [InlineKeyboardButton("📄 文档文件", callback_data="media_document")],
        [InlineKeyboardButton("🔙 返回", callback_data="menu_tasks")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_parse_mode_keyboard() -> InlineKeyboardMarkup:
    """获取解析模式选择键盘 - TeleRaptor 风格的格式化支持"""
    keyboard = [
        [InlineKeyboardButton("📝 Markdown 格式", callback_data="parse_markdown")],
        [InlineKeyboardButton("🌐 HTML 格式", callback_data="parse_html")],
        [InlineKeyboardButton("⚫ 无格式（纯文本）", callback_data="parse_none")],
        [InlineKeyboardButton("🔙 返回", callback_data="menu_tasks")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== 机器人处理器 ====================

# 全局变量
db_manager: DatabaseManager = None
encryptor: Encryptor = None
account_manager: AccountManager = None
task_manager: TaskManager = None
message_sender: MessageSender = None


def check_user_permission(user_id: int) -> bool:
    """检查用户权限"""
    if not ALLOWED_USERS:
        return True  # 如果没有配置白名单，允许所有用户
    return user_id in ALLOWED_USERS


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """启动处理器 - 显示主菜单"""
    user = update.effective_user
    
    # 检查权限
    if not check_user_permission(user.id):
        await update.message.reply_text("❌ 您没有权限使用此机器人。")
        return
    
    # 创建或获取用户
    db_manager.get_or_create_user(user.id, user.username)
    
    welcome_text = f"""
👋 欢迎使用 Telegram 私信机器人管理系统！

您好，{user.first_name}！

这是一个功能强大的私信发送管理系统，您可以：
• 管理多个 Telegram 账户
• 创建批量私信任务
• 监控发送进度和状态
• 配置发送参数和限制

请选择下方的功能按钮开始使用：
"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard()
    )


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """按钮回调处理器"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # 检查权限
    if not check_user_permission(user_id):
        await query.edit_message_text("❌ 您没有权限使用此机器人。")
        return
    
    data = query.data
    
    # 主菜单
    if data == "back_main":
        await query.edit_message_text(
            "🏠 主菜单\n\n请选择功能：",
            reply_markup=get_main_menu_keyboard()
        )
    
    # 账户管理菜单
    elif data == "menu_accounts":
        await query.edit_message_text(
            "📱 账户管理\n\n请选择操作：",
            reply_markup=get_accounts_menu_keyboard()
        )
    
    # 添加账户
    elif data == "account_add":
        await query.edit_message_text(
            "➕ 添加账户\n\n请选择添加方式：",
            reply_markup=get_account_add_method_keyboard()
        )
    
    # 通过 Session String 添加账户
    elif data == "account_add_session":
        await query.edit_message_text(
            "🔑 通过 Session String 添加账户\n\n"
            "请发送您的 Telegram Session String：\n"
            "（从 Telethon 导出的会话字符串）\n\n"
            "格式示例：\n"
            "1AQAAAAAZ4BH6vUGAgm...",
            reply_markup=get_back_keyboard("menu_accounts")
        )
        context.user_data['waiting_for'] = 'session_string'
        return WAITING_SESSION_STRING
    
    # 通过 Session JSON 文件添加账户
    elif data == "account_add_json":
        await query.edit_message_text(
            "📄 通过 Session JSON 文件添加账户\n\n"
            "请上传 Telethon session JSON 文件：\n"
            "• 支持标准 Telethon session.json 格式\n"
            "• 支持 ZIP 压缩包（自动解压第一个 JSON 文件）\n"
            "• 支持多种编码（UTF-8, GBK, GB2312 等）\n\n"
            "JSON 格式示例：\n"
            "{\n"
            '  "dc_id": 2,\n'
            '  "server_address": "149.154.167.51",\n'
            '  "port": 443,\n'
            '  "auth_key": "base64编码的认证密钥",\n'
            '  "takeout_id": null\n'
            "}",
            reply_markup=get_back_keyboard("menu_accounts")
        )
        context.user_data['waiting_for'] = 'session_json'
        return WAITING_SESSION_STRING
    
    # 通过 TData 文件夹添加账户
    elif data == "account_add_tdata":
        await query.edit_message_text(
            "📁 通过 TData 文件夹添加账户\n\n"
            "请上传 TData 文件夹中的文件：\n"
            "• 需要上传 key_datas 文件\n"
            "• 可选上传其他 tdata 相关文件\n\n"
            "⚠️ 注意：\n"
            "TData 文件来自 Telegram Desktop\n"
            "路径通常在：\n"
            "• Windows: %APPDATA%\\Telegram Desktop\\tdata\n"
            "• Linux: ~/.local/share/TelegramDesktop/tdata\n"
            "• macOS: ~/Library/Application Support/Telegram Desktop/tdata\n\n"
            "请将整个 tdata 文件夹打包为 ZIP 后上传",
            reply_markup=get_back_keyboard("menu_accounts")
        )
        context.user_data['waiting_for'] = 'tdata_file'
        return WAITING_SESSION_STRING
    
    # 通过手机号添加账户
    elif data == "account_add_phone":
        await query.edit_message_text(
            "📞 通过手机号+验证码添加账户\n\n"
            "步骤 1/2: 请发送您的手机号\n\n"
            "格式：+国家代码 手机号\n"
            "例如：\n"
            "• +86 138xxxxxxxx（中国）\n"
            "• +1 2025551234（美国）\n"
            "• +7 9161234567（俄罗斯）",
            reply_markup=get_back_keyboard("menu_accounts")
        )
        context.user_data['waiting_for'] = 'phone_number'
        context.user_data['phone_login'] = {}
        return WAITING_PHONE_NUMBER
    
    # 账户列表
    elif data == "account_list":
        accounts = account_manager.get_user_accounts(user_id)
        
        if not accounts:
            await query.edit_message_text(
                "📋 账户列表\n\n"
                "暂无账户，请先添加账户。",
                reply_markup=get_back_keyboard("menu_accounts")
            )
        else:
            text = "📋 账户列表\n\n"
            for i, acc in enumerate(accounts, 1):
                status_emoji = "✅" if acc.status == "active" else "❌" if acc.status == "banned" else "⚠️"
                text += f"{i}. {status_emoji} {acc.phone_number or 'N/A'}\n"
                text += f"   状态: {acc.status}\n"
                text += f"   今日已发: {acc.messages_sent_today or 0}\n"
                text += f"   创建时间: {acc.created_at.strftime('%Y-%m-%d')}\n\n"
            
            await query.edit_message_text(
                text,
                reply_markup=get_back_keyboard("menu_accounts")
            )
    
    # 任务管理菜单
    elif data == "menu_tasks":
        await query.edit_message_text(
            "📝 任务管理\n\n请选择操作：",
            reply_markup=get_tasks_menu_keyboard()
        )
    
    # 创建新任务
    elif data == "task_new":
        # 检查是否有账户
        accounts = account_manager.get_user_accounts(user_id)
        if not accounts:
            await query.edit_message_text(
                "❌ 创建任务失败\n\n"
                "您还没有添加任何账户，请先添加账户。",
                reply_markup=get_back_keyboard("menu_tasks")
            )
            return
        
        # 步骤1：选择媒体类型 - TeleRaptor 风格
        await query.edit_message_text(
            "➕ 创建新任务\n\n"
            "步骤 1/5: 选择消息类型\n\n"
            "请选择要发送的消息类型：",
            reply_markup=get_media_type_keyboard()
        )
        context.user_data['task_data'] = {}
        return
    
    # 选择媒体类型
    elif data.startswith("media_"):
        media_type = data.split("_")[1]
        context.user_data['task_data'] = {'media_type': media_type}
        
        # 媒体类型名称映射
        media_type_names = {
            'text': '📝 纯文本',
            'photo': '🖼️ 图片',
            'video': '🎥 视频',
            'voice': '🎤 语音',
            'document': '📄 文档'
        }
        selected_name = media_type_names.get(media_type, '📝 纯文本')
        
        # 步骤2：选择格式化模式
        await query.edit_message_text(
            f"➕ 创建新任务\n\n"
            f"已选择: {selected_name}\n\n"
            f"步骤 2/5: 选择文本格式化\n\n"
            f"请选择消息文本的格式化方式：",
            reply_markup=get_parse_mode_keyboard()
        )
        return
    
    # 选择解析模式
    elif data.startswith("parse_"):
        parse_mode = data.split("_")[1]
        if parse_mode == 'none':
            parse_mode = None
        elif parse_mode == 'markdown':
            parse_mode = 'Markdown'
        elif parse_mode == 'html':
            parse_mode = 'HTML'
        
        context.user_data['task_data']['parse_mode'] = parse_mode
        
        # 步骤3：输入消息模板
        format_help = ""
        if parse_mode == 'Markdown':
            format_help = "\n\n🎨 Markdown 格式化语法：\n" \
                         "**粗体** - 粗体文字\n" \
                         "*斜体* - 斜体文字\n" \
                         "[链接文字](URL) - 超链接\n" \
                         "`代码` - 代码样式"
        elif parse_mode == 'HTML':
            format_help = "\n\n🎨 HTML 格式化语法：\n" \
                         "<b>粗体</b> - 粗体文字\n" \
                         "<i>斜体</i> - 斜体文字\n" \
                         "<a href='URL'>链接</a> - 超链接\n" \
                         "<code>代码</code> - 代码样式"
        
        await query.edit_message_text(
            "➕ 创建新任务\n\n"
            "步骤 3/5: 请输入消息模板\n\n"
            "✨ 个性化变量（TeleRaptor 风格）：\n"
            "{name} - 用户名或名字\n"
            "{first_name} - 名字\n"
            "{last_name} - 姓氏\n"
            "{full_name} - 全名\n"
            "{username} - @用户名"
            f"{format_help}\n\n"
            "例如: 你好 **{name}**，这是一条测试消息！",
            reply_markup=get_back_keyboard("menu_tasks")
        )
        context.user_data['waiting_for'] = 'message_template'
        return WAITING_MESSAGE_TEMPLATE
    
    # 任务列表
    elif data == "task_list":
        tasks = task_manager.get_user_tasks(user_id)
        
        if not tasks:
            await query.edit_message_text(
                "📋 任务列表\n\n"
                "暂无任务，请先创建任务。",
                reply_markup=get_back_keyboard("menu_tasks")
            )
        else:
            # 创建任务列表按钮
            keyboard = []
            for task in tasks[:10]:  # 只显示最近10个任务
                status_emoji = {
                    'pending': '⏳',
                    'running': '▶️',
                    'completed': '✅',
                    'failed': '❌',
                    'stopped': '⏸️'
                }.get(task.status, '❓')
                
                button_text = f"{status_emoji} 任务 #{task.id} - {task.status}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"task_view_{task.id}")])
            
            keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_tasks")])
            
            await query.edit_message_text(
                "📋 任务列表\n\n点击任务查看详情：",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    # 查看任务详情
    elif data.startswith("task_view_"):
        task_id = int(data.split("_")[2])
        task = task_manager.get_task(task_id)
        
        if not task:
            await query.edit_message_text("❌ 任务不存在")
            return
        
        progress = task.progress or {}
        text = f"""
📊 任务详情 #{task.id}

状态: {task.status}
消息模板: {task.message_template[:50]}...
目标数量: {progress.get('total', 0)}
已发送: {progress.get('sent', 0)}
失败: {progress.get('failed', 0)}
创建时间: {task.created_at.strftime('%Y-%m-%d %H:%M')}
"""
        
        if task.started_at:
            text += f"开始时间: {task.started_at.strftime('%Y-%m-%d %H:%M')}\n"
        if task.completed_at:
            text += f"完成时间: {task.completed_at.strftime('%Y-%m-%d %H:%M')}\n"
        
        await query.edit_message_text(
            text,
            reply_markup=get_task_action_keyboard(task_id, task.status)
        )
    
    # 开始执行任务
    elif data.startswith("task_start_"):
        task_id = int(data.split("_")[2])
        
        # 在后台启动任务
        asyncio.create_task(message_sender.send_task(task_id))
        
        await query.edit_message_text(
            f"✅ 任务 #{task_id} 已开始执行！\n\n"
            "任务将在后台运行，您可以随时查看进度。",
            reply_markup=get_back_keyboard("task_list")
        )
    
    # 停止任务
    elif data.startswith("task_stop_"):
        task_id = int(data.split("_")[2])
        task_manager.stop_task(task_id)
        
        await query.edit_message_text(
            f"⏸️ 任务 #{task_id} 已停止！",
            reply_markup=get_back_keyboard("task_list")
        )
    
    # 全局设置菜单
    elif data == "menu_settings":
        text = f"""
⚙️ 全局设置

当前配置：
• 每账户每日最大发送: {MAX_MESSAGES_PER_ACCOUNT_PER_DAY} 条
• 最小延迟: {MIN_DELAY_SECONDS} 秒
• 最大延迟: {MAX_DELAY_SECONDS} 秒

（配置修改请编辑 .env 文件）
"""
        await query.edit_message_text(
            text,
            reply_markup=get_back_keyboard("back_main")
        )
    
    # 帮助文档
    elif data == "menu_help":
        help_text = """
❓ 帮助文档

📱 账户管理：
• 添加账户：支持通过 Session String 或手机号添加
• 账户列表：查看所有账户状态和发送统计

📝 任务管理：
• 创建任务：设置消息模板、目标列表、选择账户
• 任务列表：查看任务状态和执行进度
• 开始/停止：控制任务执行

⚙️ 全局设置：
• 发送延迟：避免频率限制
• 每日限制：保护账户安全

🔒 安全提示：
• Session String 会加密存储
• 建议设置合理的发送延迟
• 监控账户状态，及时处理异常

⚠️ 免责声明：
请遵守 Telegram 服务条款，不要发送垃圾信息。
"""
        await query.edit_message_text(
            help_text,
            reply_markup=get_back_keyboard("back_main")
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """消息处理器 - 处理用户输入"""
    user_id = update.effective_user.id
    text = update.message.text if update.message.text else ""
    
    waiting_for = context.user_data.get('waiting_for')
    
    # 处理 Session String 输入
    if waiting_for == 'session_string':
        try:
            # 验证 session string（简单验证）
            if len(text) < 50:
                await update.message.reply_text(
                    "❌ Session String 格式不正确，请重新输入。",
                    reply_markup=get_back_keyboard("menu_accounts")
                )
                return
            
            # 添加账户
            user = db_manager.get_or_create_user(user_id, update.effective_user.username)
            account_manager.add_account(user.id, text)
            
            await update.message.reply_text(
                "✅ 账户添加成功！",
                reply_markup=get_accounts_menu_keyboard()
            )
            
            context.user_data['waiting_for'] = None
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"添加账户失败: {e}")
            await update.message.reply_text(
                f"❌ 添加账户失败: {str(e)}",
                reply_markup=get_back_keyboard("menu_accounts")
            )
    
    # 处理 Session JSON 文件
    elif waiting_for == 'session_json':
        # 检查是否有文档
        if update.message.document:
            temp_file_path = None
            try:
                file = await update.message.document.get_file()
                file_content = await file.download_as_bytearray()
                file_name = update.message.document.file_name or ''
                
                # 检查是否是 ZIP 文件
                if file_name.endswith('.zip'):
                    # 保存到临时文件
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                        tmp_file.write(file_content)
                        tmp_file.flush()
                        temp_file_path = tmp_file.name
                    
                    try:
                        # 解压并查找 JSON 文件
                        with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                            json_files = [f for f in zip_ref.namelist() if f.endswith('.json')]
                            
                            if not json_files:
                                await update.message.reply_text(
                                    "❌ ZIP 文件中没有找到 JSON 文件",
                                    reply_markup=get_back_keyboard("menu_accounts")
                                )
                                return
                            
                            # 处理第一个 JSON 文件
                            json_file_name = json_files[0]
                            
                            # 验证路径安全性 - 防止目录遍历攻击
                            if '..' in json_file_name or json_file_name.startswith('/'):
                                await update.message.reply_text(
                                    "❌ 检测到不安全的文件路径",
                                    reply_markup=get_back_keyboard("menu_accounts")
                                )
                                return
                            
                            json_content = zip_ref.read(json_file_name)
                            file_content = json_content
                    finally:
                        # 确保临时文件被删除
                        if temp_file_path and os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                
                # 尝试多种编码解码文件
                encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'gbk', 'gb2312', 'gb18030']
                decoded_content = None
                used_encoding = None
                
                for encoding in encodings:
                    try:
                        decoded_content = file_content.decode(encoding)
                        used_encoding = encoding
                        logger.info(f"成功使用 {encoding} 编码解码文件")
                        break
                    except UnicodeDecodeError:
                        continue
                
                if decoded_content is None:
                    await update.message.reply_text(
                        "❌ 无法解码文件内容\n\n"
                        "请确保文件是有效的文本文件（JSON 格式）\n"
                        "支持的编码：UTF-8, GBK, GB2312, Latin-1",
                        reply_markup=get_back_keyboard("menu_accounts")
                    )
                    return
                
                # 解析 JSON - Telethon session format
                session_data = json.loads(decoded_content)
                
                # 验证必需字段
                required_fields = ['dc_id', 'server_address', 'port', 'auth_key']
                missing_fields = [f for f in required_fields if f not in session_data]
                
                if missing_fields:
                    await update.message.reply_text(
                        f"❌ JSON 文件缺少必需字段: {', '.join(missing_fields)}\n\n"
                        "Telethon session JSON 格式示例：\n"
                        '{\n'
                        '  "dc_id": 2,\n'
                        '  "server_address": "149.154.167.51",\n'
                        '  "port": 443,\n'
                        '  "auth_key": "base64_encoded_auth_key",\n'
                        '  "takeout_id": null\n'
                        '}',
                        reply_markup=get_back_keyboard("menu_accounts")
                    )
                    return
                
                # 转换 session JSON 为 StringSession 格式
                try:
                    from telethon.crypto import AuthKey
                    import struct
                    import ipaddress
                    
                    dc_id = session_data['dc_id']
                    server_address = session_data['server_address']
                    port = session_data['port']
                    auth_key_b64 = session_data['auth_key']
                    
                    # 解码 auth_key
                    auth_key_bytes = base64.b64decode(auth_key_b64)
                    
                    # 创建 AuthKey 对象
                    auth_key = AuthKey(data=auth_key_bytes)
                    
                    # 转换 IP 为打包格式
                    ip = ipaddress.ip_address(server_address).packed
                    
                    # 打包数据
                    _STRUCT_PREFORMAT = '>B{}sH256s'
                    packed_data = struct.pack(
                        _STRUCT_PREFORMAT.format(len(ip)),
                        dc_id,
                        ip,
                        port,
                        auth_key.key
                    )
                    
                    # 编码为 StringSession 格式
                    CURRENT_VERSION = '1'
                    session_string = CURRENT_VERSION + base64.urlsafe_b64encode(packed_data).decode('ascii')
                    
                    logger.info(f"成功转换 session JSON 为 StringSession 格式")
                    
                except Exception as e:
                    logger.error(f"转换 session 失败: {e}")
                    await update.message.reply_text(
                        f"❌ 转换 session 失败: {str(e)}\n\n"
                        "请确保 auth_key 是有效的 base64 编码字符串",
                        reply_markup=get_back_keyboard("menu_accounts")
                    )
                    return
                
                # 提取手机号（可选）
                phone_number = session_data.get('phone') or session_data.get('phone_number')
                
                # 添加账户
                user = db_manager.get_or_create_user(user_id, update.effective_user.username)
                account_manager.add_account(user.id, session_string, phone_number)
                
                await update.message.reply_text(
                    f"✅ 账户添加成功！\n手机号: {phone_number or 'N/A'}",
                    reply_markup=get_accounts_menu_keyboard()
                )
                
                context.user_data['waiting_for'] = None
                return ConversationHandler.END
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {e}")
                await update.message.reply_text(
                    "❌ JSON 文件格式错误，请检查文件内容\n\n"
                    "确保文件是有效的 JSON 格式，例如：\n"
                    '{\n'
                    '  "session_string": "1AQAA...",\n'
                    '  "phone": "+86138xxxxxxxx"\n'
                    '}',
                    reply_markup=get_back_keyboard("menu_accounts")
                )
            except Exception as e:
                logger.error(f"添加账户失败: {e}")
                await update.message.reply_text(
                    f"❌ 添加账户失败: {str(e)}",
                    reply_markup=get_back_keyboard("menu_accounts")
                )
            finally:
                # 确保临时文件被清理（如果在 try 块之外创建）
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                    except Exception:
                        pass
        else:
            await update.message.reply_text(
                "❌ 请上传 JSON 文件",
                reply_markup=get_back_keyboard("menu_accounts")
            )
    
    # 处理 TData 文件
    elif waiting_for == 'tdata_file':
        if update.message.document:
            try:
                file = await update.message.document.get_file()
                
                # 检查是否是 ZIP 文件
                if not update.message.document.file_name.endswith('.zip'):
                    await update.message.reply_text(
                        "❌ 请上传 ZIP 格式的 tdata 文件夹压缩包",
                        reply_markup=get_back_keyboard("menu_accounts")
                    )
                    return
                
                # 下载文件
                import tempfile
                import zipfile
                from pathlib import Path
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                    await file.download_to_drive(tmp_file.name)
                    
                    # 解压文件
                    with zipfile.ZipFile(tmp_file.name, 'r') as zip_ref:
                        extract_dir = tempfile.mkdtemp()
                        zip_ref.extractall(extract_dir)
                        
                        # 查找 key_datas 文件
                        key_datas_path = None
                        for root, dirs, files in os.walk(extract_dir):
                            if 'key_datas' in files:
                                key_datas_path = os.path.join(root, 'key_datas')
                                break
                        
                        if not key_datas_path:
                            await update.message.reply_text(
                                "❌ 未找到 key_datas 文件，请确认上传的是正确的 tdata 文件夹",
                                reply_markup=get_back_keyboard("menu_accounts")
                            )
                            return
                        
                        # TODO: 这里需要实现 TData 到 Session String 的转换
                        # 这需要使用 opentele 或类似库来转换
                        await update.message.reply_text(
                            "⚠️ TData 转换功能开发中\n\n"
                            "建议使用以下方式：\n"
                            "1. 使用 Session String 方式\n"
                            "2. 使用 Session JSON 文件方式\n"
                            "3. 使用手机号+验证码方式",
                            reply_markup=get_back_keyboard("menu_accounts")
                        )
                        
                        # 清理临时文件
                        import shutil
                        shutil.rmtree(extract_dir)
                        os.unlink(tmp_file.name)
                
            except Exception as e:
                logger.error(f"处理 TData 文件失败: {e}")
                await update.message.reply_text(
                    f"❌ 处理文件失败: {str(e)}",
                    reply_markup=get_back_keyboard("menu_accounts")
                )
        else:
            await update.message.reply_text(
                "❌ 请上传 ZIP 文件",
                reply_markup=get_back_keyboard("menu_accounts")
            )
    
    # 处理手机号输入
    elif waiting_for == 'phone_number':
        try:
            # 清理手机号格式
            phone = text.strip().replace(' ', '').replace('-', '')
            
            if not phone.startswith('+'):
                await update.message.reply_text(
                    "❌ 手机号格式错误，必须包含国家代码\n"
                    "例如: +86 138xxxxxxxx",
                    reply_markup=get_back_keyboard("menu_accounts")
                )
                return
            
            # 保存手机号并发送验证码
            context.user_data['phone_login']['phone'] = phone
            
            # 创建 Telethon 客户端并发送验证码
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            
            # 发送验证码
            result = await client.send_code_request(phone)
            context.user_data['phone_login']['phone_code_hash'] = result.phone_code_hash
            context.user_data['phone_login']['client_session'] = client.session.save()
            
            await client.disconnect()
            
            await update.message.reply_text(
                f"📲 验证码已发送到 {phone}\n\n"
                f"步骤 2/2: 请输入收到的验证码\n\n"
                f"格式：12345（5位数字）",
                reply_markup=get_back_keyboard("menu_accounts")
            )
            
            context.user_data['waiting_for'] = 'verification_code'
            return WAITING_VERIFICATION_CODE
            
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            await update.message.reply_text(
                f"❌ 发送验证码失败: {str(e)}\n\n"
                f"可能的原因：\n"
                f"• 手机号格式错误\n"
                f"• API_ID 或 API_HASH 配置错误\n"
                f"• 网络连接问题",
                reply_markup=get_back_keyboard("menu_accounts")
            )
            context.user_data['waiting_for'] = None
    
    # 处理验证码输入
    elif waiting_for == 'verification_code':
        try:
            code = text.strip().replace(' ', '').replace('-', '')
            
            phone_login = context.user_data.get('phone_login', {})
            phone = phone_login.get('phone')
            phone_code_hash = phone_login.get('phone_code_hash')
            saved_session = phone_login.get('client_session')
            
            if not all([phone, phone_code_hash, saved_session]):
                await update.message.reply_text(
                    "❌ 会话已过期，请重新开始",
                    reply_markup=get_back_keyboard("menu_accounts")
                )
                context.user_data['waiting_for'] = None
                return
            
            # 使用验证码登录
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            
            client = TelegramClient(StringSession(saved_session), API_ID, API_HASH)
            await client.connect()
            
            try:
                # 尝试使用验证码登录
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except Exception as e:
                error_str = str(e).lower()
                if 'password' in error_str or 'two-step' in error_str:
                    # 需要两步验证密码
                    await update.message.reply_text(
                        "🔐 账户启用了两步验证\n\n"
                        "请输入您的两步验证密码：",
                        reply_markup=get_back_keyboard("menu_accounts")
                    )
                    context.user_data['waiting_for'] = 'two_factor_password'
                    await client.disconnect()
                    return
                else:
                    raise
            
            # 获取 session string
            session_string = client.session.save()
            await client.disconnect()
            
            # 添加账户
            user = db_manager.get_or_create_user(user_id, update.effective_user.username)
            account_manager.add_account(user.id, session_string, phone)
            
            await update.message.reply_text(
                f"✅ 账户添加成功！\n"
                f"手机号: {phone}",
                reply_markup=get_accounts_menu_keyboard()
            )
            
            context.user_data['waiting_for'] = None
            context.user_data['phone_login'] = {}
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"验证码登录失败: {e}")
            await update.message.reply_text(
                f"❌ 登录失败: {str(e)}\n\n"
                f"可能的原因：\n"
                f"• 验证码错误或已过期\n"
                f"• 请重新开始添加流程",
                reply_markup=get_back_keyboard("menu_accounts")
            )
            context.user_data['waiting_for'] = None
            context.user_data['phone_login'] = {}
    
    # 处理两步验证密码
    elif waiting_for == 'two_factor_password':
        try:
            password = text.strip()
            
            phone_login = context.user_data.get('phone_login', {})
            phone = phone_login.get('phone')
            saved_session = phone_login.get('client_session')
            
            if not all([phone, saved_session]):
                await update.message.reply_text(
                    "❌ 会话已过期，请重新开始",
                    reply_markup=get_back_keyboard("menu_accounts")
                )
                context.user_data['waiting_for'] = None
                return
            
            # 使用密码完成登录
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            
            client = TelegramClient(StringSession(saved_session), API_ID, API_HASH)
            await client.connect()
            
            await client.sign_in(password=password)
            
            # 获取 session string
            session_string = client.session.save()
            await client.disconnect()
            
            # 添加账户
            user = db_manager.get_or_create_user(user_id, update.effective_user.username)
            account_manager.add_account(user.id, session_string, phone)
            
            await update.message.reply_text(
                f"✅ 账户添加成功！\n"
                f"手机号: {phone}",
                reply_markup=get_accounts_menu_keyboard()
            )
            
            context.user_data['waiting_for'] = None
            context.user_data['phone_login'] = {}
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"两步验证失败: {e}")
            await update.message.reply_text(
                f"❌ 密码错误: {str(e)}\n\n"
                f"请重新开始添加流程",
                reply_markup=get_back_keyboard("menu_accounts")
            )
            context.user_data['waiting_for'] = None
            context.user_data['phone_login'] = {}
    
    # 处理消息模板输入
    elif waiting_for == 'message_template':
        context.user_data['task_data']['message_template'] = text
        
        media_type = context.user_data['task_data'].get('media_type', 'text')
        
        # 媒体类型名称映射
        media_file_names = {
            'photo': '图片',
            'video': '视频',
            'voice': '语音',
            'document': '文档'
        }
        
        # 如果需要媒体文件，要求上传
        if media_type in ['photo', 'video', 'voice', 'document']:
            file_type_name = media_file_names.get(media_type, '文件')
            await update.message.reply_text(
                f"✅ 消息模板已保存\n\n"
                f"步骤 4/5: 请上传{file_type_name}文件\n\n"
                f"请直接发送文件到这里。",
                reply_markup=get_back_keyboard("menu_tasks")
            )
            context.user_data['waiting_for'] = 'media_file'
            return
        else:
            # 纯文本消息，跳过媒体上传
            await update.message.reply_text(
                "✅ 消息模板已保存\n\n"
                "步骤 4/5: 请输入目标用户列表\n\n"
                "📋 支持多种格式：\n"
                "• 每行一个用户名: @username\n"
                "• 每行一个用户ID: 123456789\n"
                "• 混合格式\n\n"
                "例如：\n"
                "@username1\n"
                "@username2\n"
                "123456789",
                reply_markup=get_back_keyboard("menu_tasks")
            )
            context.user_data['waiting_for'] = 'target_list'
            return WAITING_TARGET_LIST
    
    # 处理目标列表输入
    elif waiting_for == 'target_list':
        targets = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not targets:
            await update.message.reply_text(
                "❌ 目标列表不能为空，请重新输入。",
                reply_markup=get_back_keyboard("menu_tasks")
            )
            return
        
        context.user_data['task_data']['target_list'] = targets
        
        # 获取用户账户
        accounts = account_manager.get_user_accounts(user_id)
        active_accounts = [acc for acc in accounts if acc.status == 'active']
        
        if not active_accounts:
            await update.message.reply_text(
                "❌ 没有可用的活跃账户，请先添加账户。",
                reply_markup=get_back_keyboard("menu_tasks")
            )
            return
        
        # 创建任务（使用所有活跃账户）
        user = db_manager.get_or_create_user(user_id, update.effective_user.username)
        account_ids = [acc.id for acc in active_accounts]
        
        task_data = context.user_data.get('task_data', {})
        
        task = task_manager.create_task(
            user_id=user_id,
            message_template=task_data.get('message_template', ''),
            target_list=targets,
            account_ids=account_ids,
            config={
                'min_delay': MIN_DELAY_SECONDS,
                'max_delay': MAX_DELAY_SECONDS,
                'max_per_account': MAX_MESSAGES_PER_ACCOUNT_PER_DAY
            },
            media_type=task_data.get('media_type', 'text'),
            media_url=task_data.get('media_url'),
            parse_mode=task_data.get('parse_mode', 'Markdown')
        )
        
        media_type_name = {
            'text': '📝 纯文本',
            'photo': '🖼️ 图片',
            'video': '🎥 视频',
            'voice': '🎤 语音',
            'document': '📄 文档'
        }.get(task_data.get('media_type', 'text'), '📝 纯文本')
        
        await update.message.reply_text(
            f"✅ 任务创建成功！\n\n"
            f"📋 任务信息：\n"
            f"任务 ID: #{task.id}\n"
            f"消息类型: {media_type_name}\n"
            f"目标数量: {len(targets)}\n"
            f"使用账户: {len(account_ids)} 个\n"
            f"格式化: {task_data.get('parse_mode', 'Markdown') or '无'}\n\n"
            f"✨ 任务已就绪，可以开始执行！",
            reply_markup=get_tasks_menu_keyboard()
        )
        
        context.user_data['waiting_for'] = None
        context.user_data['task_data'] = {}
        return ConversationHandler.END
    
    # 默认回复
    else:
        await update.message.reply_text(
            "请使用下方按钮进行操作。",
            reply_markup=get_main_menu_keyboard()
        )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消处理器"""
    context.user_data.clear()
    await update.message.reply_text(
        "操作已取消。",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


# ==================== 主程序 ====================

def main():
    """主程序入口"""
    global db_manager, encryptor, account_manager, task_manager, message_sender
    
    # 检查配置
    if not BOT_TOKEN:
        logger.error("请在 .env 文件中配置 BOT_TOKEN")
        return
    
    if not API_ID or not API_HASH:
        logger.error("请在 .env 文件中配置 API_ID 和 API_HASH")
        return
    
    # 初始化组件
    logger.info("初始化数据库...")
    db_manager = DatabaseManager(DATABASE_URL)
    
    logger.info("初始化加密器...")
    encryptor = Encryptor(ENCRYPTION_KEY)
    
    logger.info("初始化管理器...")
    account_manager = AccountManager(db_manager, encryptor)
    task_manager = TaskManager(db_manager)
    message_sender = MessageSender(db_manager, encryptor, account_manager, task_manager)
    
    # 创建应用
    logger.info("启动机器人...")
    application = Application.builder().token(BOT_TOKEN).build()
    
    # 添加处理器
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, message_handler))  # 文档处理
    
    # 启动机器人
    logger.info("机器人已启动，按 Ctrl+C 停止")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
