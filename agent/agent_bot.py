#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
华南代理机器人（统一通知 + 纯二维码 + 北京时间显示 + 10分钟有效 + 取消订单修复版）
特性:
- 固定地址 + 4 位识别金额自动到账（唯一识别码写入金额小数部分）
- 商品/价格管理、利润提现、统计报表
- 充值/购买/提现群内通知统一使用 HEADQUARTERS_NOTIFY_CHAT_ID
- 充值界面：点击金额后只发送 1 条消息（纯二维码图片 + caption 文案 + 按钮）
- 有效期统一为 10 分钟；caption 中以北京时间显示“有效期至”；超时自动标记 expired
- 二维码内容仅为纯地址（不含 tron: 前缀和 amount 参数），提升钱包兼容性
- 取消订单修复：支持删除原二维码消息或编辑其 caption（通过 RECHARGE_DELETE_ON_CANCEL 环境变量控制）
"""

import os
import sys
import logging
import traceback
import zipfile
import time
import random
import requests
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pymongo import MongoClient
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
from bson import ObjectId
from html import escape as html_escape
from pathlib import Path
from io import BytesIO
from typing import Union
# 二维码与图片
try:
    import qrcode
    from PIL import Image
except Exception as _qr_import_err:
    qrcode = None
    Image = None
    print(f"⚠️ 二维码依赖未就绪(qrcode/Pillow)，将回退纯文本: {_qr_import_err}")

# ================= 环境变量加载（支持 --env / ENV_FILE / 默认 .env） =================
def _resolve_env_file(argv: list) -> Path:
    env_file_cli = None
    for i, a in enumerate(argv):
        if a == "--env" and i + 1 < len(argv):
            env_file_cli = argv[i + 1]
            break
        if a.startswith("--env="):
            env_file_cli = a.split("=", 1)[1].strip()
            break
    env_file_env = os.getenv("ENV_FILE")
    filename = env_file_cli or env_file_env or ".env"
    p = Path(__file__).parent / filename
    return p

try:
    from dotenv import load_dotenv
    env_path = _resolve_env_file(sys.argv)
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ 已加载环境文件: {env_path}")
    else:
        print(f"ℹ️ 未找到环境文件 {env_path}，使用系统环境变量")
except Exception as e:
    print(f"⚠️ 环境文件加载失败: {e}")

# ================= 日志配置 =================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("agent_bot")

# 管理员
ADMIN_USERS = [7004496404]

# 通知群 / 频道
# ✅ 代理自己的通知群（订单、充值、提现通知发这里）
AGENT_NOTIFY_CHAT_ID = os.getenv("AGENT_NOTIFY_CHAT_ID")

# ✅ 总部通知群（代理用来监听总部补货等通知）
HEADQUARTERS_NOTIFY_CHAT_ID = os.getenv("HQ_NOTIFY_CHAT_ID") or os.getenv("HEADQUARTERS_NOTIFY_CHAT_ID")

class AgentBotConfig:
    """代理机器人配置"""
    def __init__(self):
        if len(sys.argv) > 1 and not sys.argv[-1].startswith("--env"):
            self.BOT_TOKEN = sys.argv[1]
        else:
            env_token = os.getenv("BOT_TOKEN")
            if not env_token:
                raise ValueError("请提供机器人Token：命令行参数 <BOT_TOKEN> 或环境变量 BOT_TOKEN")
            self.BOT_TOKEN = env_token

        self.MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017/")
        self.DATABASE_NAME = os.getenv("DATABASE_NAME", "9haobot")
        self.AGENT_BOT_ID = os.getenv("AGENT_BOT_ID", "62448807124351dfe5cc48d4")
        self.AGENT_NAME = os.getenv("AGENT_NAME", "华南代理机器人")
        self.FILE_BASE_PATH = os.getenv("FILE_BASE_PATH", "/www/9haobot/222/9hao-main")

        self.AGENT_USDT_ADDRESS = os.getenv("AGENT_USDT_ADDRESS")
        if not self.AGENT_USDT_ADDRESS:
            raise ValueError("未设置 AGENT_USDT_ADDRESS，请在环境变量中配置代理收款地址（TRC20）")

        # 有效期设为 10 分钟（可用环境变量覆盖）
        self.RECHARGE_EXPIRE_MINUTES = int(os.getenv("RECHARGE_EXPIRE_MINUTES", "10"))
        if self.RECHARGE_EXPIRE_MINUTES <= 0:
            self.RECHARGE_EXPIRE_MINUTES = 10

        self.RECHARGE_MIN_USDT = Decimal(os.getenv("RECHARGE_MIN_USDT", "10")).quantize(Decimal("0.01"))
        self.RECHARGE_DECIMALS = 4
        self.RECHARGE_POLL_INTERVAL_SECONDS = int(os.getenv("RECHARGE_POLL_INTERVAL_SECONDS", "8"))
        if self.RECHARGE_POLL_INTERVAL_SECONDS < 3:
            self.RECHARGE_POLL_INTERVAL_SECONDS = 3

        self.TOKEN_SYMBOL = os.getenv("TOKEN_SYMBOL", "USDT")
        self.USDT_TRON_CONTRACT = os.getenv("USDT_TRON_CONTRACT", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
        self.TRONSCAN_TRX20_API = os.getenv("TRONSCAN_TRX20_API", "https://apilist.tronscanapi.com/api/token_trc20/transfers")

        self.TRON_API_KEYS = [k.strip() for k in os.getenv("TRON_API_KEYS", "").split(",") if k.strip()]
        self.TRONGRID_API_BASE = os.getenv("TRONGRID_API_BASE", "https://api.trongrid.io").rstrip("/")
        self.TRON_API_KEY_HEADER = os.getenv("TRON_API_KEY_HEADER", "TRON-PRO-API-KEY")
        self._tron_key_index = 0

        # ✅ 代理自己的通知群
        self.AGENT_NOTIFY_CHAT_ID = os.getenv("AGENT_NOTIFY_CHAT_ID")
        if not self.AGENT_NOTIFY_CHAT_ID:
            logger.warning("⚠️ 未设置 AGENT_NOTIFY_CHAT_ID，订单通知可能无法发送")
        
        # ✅ 总部通知群
        self.HEADQUARTERS_NOTIFY_CHAT_ID = HEADQUARTERS_NOTIFY_CHAT_ID
        if not self.HEADQUARTERS_NOTIFY_CHAT_ID:
            logger.warning("⚠️ 未设置 HEADQUARTERS_NOTIFY_CHAT_ID")

        # 取消订单后是否删除原消息 (默认删除)
        self.RECHARGE_DELETE_ON_CANCEL = os.getenv("RECHARGE_DELETE_ON_CANCEL", "1") in ("1", "true", "True")

        try:
            self.client = MongoClient(self.MONGODB_URI)
            self.db = self.client[self.DATABASE_NAME]
            self.client.admin.command('ping')
            logger.info("✅ 数据库连接成功")

            self.ejfl = self.db['ejfl']
            self.hb = self.db['hb']
            self.agent_product_prices = self.db['agent_product_prices']
            self.agent_profit_account = self.db['agent_profit_account']
            self.withdrawal_requests = self.db['withdrawal_requests']
            self.recharge_orders = self.db['recharge_orders']
        except Exception as e:
            logger.error(f"❌ 数据库连接失败: {e}")
            raise

    def get_agent_user_collection(self):
        return self.db[f'agent_users_{self.AGENT_BOT_ID}']

    def get_agent_gmjlu_collection(self):
        return self.db[f'agent_gmjlu_{self.AGENT_BOT_ID}']

    def _next_tron_api_key(self) -> Optional[str]:
        if not self.TRON_API_KEYS:
            return None
        key = self.TRON_API_KEYS[self._tron_key_index % len(self.TRON_API_KEYS)]
        self._tron_key_index = (self._tron_key_index + 1) % max(len(self.TRON_API_KEYS), 1)
        return key


class AgentBotCore:
    """核心业务"""

    def __init__(self, config: AgentBotConfig):
        self.config = config

    # ---------- 时间/工具 ----------
    def _to_beijing(self, dt: datetime) -> datetime:
        """UTC -> 北京时间（UTC+8）"""
        if dt is None:
            dt = datetime.utcnow()
        return dt + timedelta(hours=8)

    # ---------- UI 辅助 ----------
    def _h(self, s: Any) -> str:
        try:
            return html_escape(str(s) if s is not None else "", quote=False)
        except Exception:
            return str(s or "")

    def _link_user(self, user_id: int) -> str:
        return f"<a href='tg://user?id={user_id}'>{user_id}</a>"

    def _tronscan_tx_url(self, tx_id: str) -> str:
        return f"https://tronscan.org/#/transaction/{tx_id}"

    def _tronscan_addr_url(self, address: str) -> str:
        return f"https://tronscan.org/#/address/{address}"

    def _kb_product_actions(self, nowuid: str, user_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🧾 查看商品", callback_data=f"product_{nowuid}"),
             InlineKeyboardButton("👤 联系用户", url=f"tg://user?id={user_id}")]
        ])

    def _kb_tx_addr_user(self, tx_id: Optional[str], address: str, user_id: int):
        btns = []
        row = []
        if tx_id:
            row.append(InlineKeyboardButton("🔎 查看交易", url=self._tronscan_tx_url(tx_id)))
        if address:
            row.append(InlineKeyboardButton("📬 查看地址", url=self._tronscan_addr_url(address)))
        if row:
            btns.append(row)
        btns.append([InlineKeyboardButton("👤 联系用户", url=f"tg://user?id={user_id}")])
        return InlineKeyboardMarkup(btns)

    # ---------- 用户与商品 ----------
    def register_user(self, user_id: int, username: str = "", first_name: str = "") -> bool:
        try:
            coll = self.config.get_agent_user_collection()
            exist = coll.find_one({'user_id': user_id})
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if exist:
                coll.update_one({'user_id': user_id}, {'$set': {'last_active': now}})
                return True
            max_user = coll.find_one({}, sort=[("count_id", -1)])
            count_id = (max_user.get('count_id', 0) + 1) if max_user else 1
            coll.insert_one({
                'user_id': user_id,
                'count_id': count_id,
                'username': username,
                'first_name': first_name,
                'fullname': first_name,
                'USDT': 0.0,
                'zgje': 0.0,
                'zgsl': 0,
                'creation_time': now,
                'register_time': now,
                'last_active': now,
                'last_contact_time': now,
                'status': 'active'
            })
            logger.info(f"✅ 用户注册成功 {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 用户注册失败: {e}")
            return False

    def get_user_info(self, user_id: int) -> Optional[Dict]:
        try:
            return self.config.get_agent_user_collection().find_one({'user_id': user_id})
        except Exception as e:
            logger.error(f"❌ 获取用户信息失败: {e}")
            return None

    def auto_sync_new_products(self):
        """自动同步总部新增商品到代理"""
        try:
            all_products = list(self.config.ejfl.find({}))
            synced = 0
            updated = 0
            
            for p in all_products:
                nowuid = p.get('nowuid')
                if not nowuid:
                    continue
                
                # ✅ 检查商品是否已存在于代理价格表
                exists = self.config.agent_product_prices.find_one({
                    'agent_bot_id': self.config.AGENT_BOT_ID,
                    'original_nowuid': nowuid
                })
                
                # ✅ 获取总部价格
                original_price = float(p.get('money', 0))
                
                if not exists:
                    # ✅ 新商品：创建代理价格记录
                    # 只有总部价格大于0的商品才同步
                    if original_price <= 0:
                        continue
                    
                    agent_markup = 0.0  # 初始无加价，后续管理员手动设置
                    self.config.agent_product_prices.insert_one({
                        'agent_bot_id': self.config.AGENT_BOT_ID,
                        'original_nowuid': nowuid,
                        'agent_markup': agent_markup,  # ✅ 存储加价（利润标记），不存储固定代理价
                        'original_price_snapshot': original_price,  # 参考用，不作实际计算
                        'product_name': p.get('projectname', ''),
                        'category': p.get('leixing') or '协议号',
                        'is_active': True,  # ✅ 新同步的商品默认激活
                        'auto_created': True,
                        'sync_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'created_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    synced += 1
                    logger.info(f"✅ 新增同步商品: {p.get('projectname')} (nowuid: {nowuid})")
                else:
                    # ✅ 已存在的商品：更新商品名称和分类（但不改变价格设置）
                    updates = {}
                    if exists.get('product_name') != p.get('projectname'):
                        updates['product_name'] = p.get('projectname', '')
                    if exists.get('category') != (p.get('leixing') or '协议号'):
                        updates['category'] = p.get('leixing') or '协议号'
                    
                    # ✅ 更新总部价格快照（仅用于参考）
                    if abs(exists.get('original_price_snapshot', 0) - original_price) > 0.01:
                        updates['original_price_snapshot'] = original_price
                    
                    if updates:
                        updates['sync_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        updates['updated_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        self.config.agent_product_prices.update_one(
                            {'agent_bot_id': self.config.AGENT_BOT_ID, 'original_nowuid': nowuid},
                            {'$set': updates}
                        )
                        updated += 1
            
            if synced > 0 or updated > 0:
                logger.info(f"✅ 商品同步完成: 新增 {synced} 个, 更新 {updated} 个")
            
            return synced
        except Exception as e:
            logger.error(f"❌ 自动同步失败: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def get_product_categories(self) -> List[Dict]:
        """获取商品分类列表（一级分类）- 仿照总部bot.py实现"""
        try:
            # ✅ 每次获取分类时自动同步新商品
            self.auto_sync_new_products()
            
            # 获取所有商品和库存信息
            all_products = list(self.config.ejfl.find({}))
            categories = {}
            
            for p in all_products:
                nowuid = p.get('nowuid')
                if not nowuid:
                    continue
                
                # ✅ 检查商品是否有价格（总部价格）
                original_price = float(p.get('money', 0))
                if original_price <= 0:
                    continue
                    
                # ✅ 检查是否是激活的代理商品
                agent_price = self.config.agent_product_prices.find_one({
                    'agent_bot_id': self.config.AGENT_BOT_ID,
                    'original_nowuid': nowuid,
                    'is_active': True
                })
                
                if not agent_price:
                    continue
                
                # 获取库存
                stock = self.config.hb.count_documents({'nowuid': nowuid, 'state': 0})
                
                # 分类名称（处理None情况）
                category = p.get('leixing') or '协议号'
                
                # 累加分类的库存
                if category not in categories:
                    categories[category] = {'name': category, 'stock': 0, 'count': 0}
                categories[category]['stock'] += stock
                categories[category]['count'] += 1
            
            # 转换为列表并按库存排序
            result = [
                {
                    '_id': cat_info['name'],
                    'stock': cat_info['stock'],
                    'count': cat_info['count']
                }
                for cat_info in categories.values()
            ]
            result.sort(key=lambda x: -x['stock'])  # 库存多的在前面
            
            return result
        except Exception as e:
            logger.error(f"❌ 获取商品分类失败: {e}")
            return []

    def get_products_by_category(self, category: str, page: int = 1, limit: int = 10) -> Dict:
        try:
            skip = (page - 1) * limit
            
            # ✅ 处理 null/空值的情况 - 协议号分类需要包括 leixing 为 null 的商品
            if category == '协议号' or category == '未分类':
                match_condition = {
                    '$or': [
                        {'leixing': None}, 
                        {'leixing': ''}, 
                        {'leixing': '协议号'},
                        {'leixing': '未分类'}
                    ]
                }
            else:
                match_condition = {'leixing': category}
            
            pipeline = [
                {'$match': match_condition},
                {'$lookup': {
                    'from': 'agent_product_prices',
                    'localField': 'nowuid',
                    'foreignField': 'original_nowuid',
                    'as': 'agent_price'
                }},
                {'$match': {
                    'agent_price.agent_bot_id': self.config.AGENT_BOT_ID,
                    'agent_price.is_active': True
                }},
                {'$skip': skip},
                {'$limit': limit}
            ]
            products = list(self.config.ejfl.aggregate(pipeline))
            
            # ✅ 统计总数时也要用同样的条件
            if category == '协议号' or category == '未分类':
                total = self.config.ejfl.count_documents({
                    '$or': [
                        {'leixing': None}, 
                        {'leixing': ''}, 
                        {'leixing': '协议号'},
                        {'leixing': '未分类'}
                    ]
                })
            else:
                total = self.config.ejfl.count_documents({'leixing': category})
            
            return {
                'products': products,
                'total': total,
                'current_page': page,
                'total_pages': (total + limit - 1) // limit
            }
        except Exception as e:
            logger.error(f"❌ 获取分类商品失败: {e}")
            return {'products': [], 'total': 0, 'current_page': 1, 'total_pages': 0}

    def get_product_stock(self, nowuid: str) -> int:
        try:
            return self.config.hb.count_documents({'nowuid': nowuid, 'state': 0})
        except Exception as e:
            logger.error(f"❌ 获取库存失败: {e}")
            return 0

    def get_product_price(self, nowuid: str) -> Optional[float]:
        try:
            # 获取商品的总部价格（实时）
            origin = self.config.ejfl.find_one({'nowuid': nowuid})
            if not origin:
                return None
            original_price = float(origin.get('money', 0.0))
            
            # 获取代理设置的加价标记
            doc = self.config.agent_product_prices.find_one({
                'agent_bot_id': self.config.AGENT_BOT_ID,
                'original_nowuid': nowuid,
                'is_active': True
            })
            if not doc:
                return None
            
            agent_markup = float(doc.get('agent_markup', 0.0))
            
            # ✅ 实时计算：代理价 = 总部价 + 加价
            agent_price = round(original_price + agent_markup, 2)
            return agent_price
        except Exception as e:
            logger.error(f"❌ 获取价格失败: {e}")
            return None

    def get_agent_product_list(self, user_id: int, page: int = 1, limit: int = 10) -> Dict:
        try:
            skip = (page - 1) * limit
            pipeline = [
                {'$lookup': {
                    'from': 'ejfl',
                    'localField': 'original_nowuid',
                    'foreignField': 'nowuid',
                    'as': 'product_info'
                }},
                {'$match': {
                    'agent_bot_id': self.config.AGENT_BOT_ID,
                    'product_info': {'$ne': []}
                }},
                {'$skip': skip},
                {'$limit': limit}
            ]
            products = list(self.config.agent_product_prices.aggregate(pipeline))
            total = self.config.agent_product_prices.count_documents({'agent_bot_id': self.config.AGENT_BOT_ID})
            return {
                'products': products,
                'total': total,
                'current_page': page,
                'total_pages': (total + limit - 1) // limit
            }
        except Exception as e:
            logger.error(f"❌ 获取代理商品失败: {e}")
            return {'products': [], 'total': 0, 'current_page': 1, 'total_pages': 0}

    def update_agent_price(self, product_nowuid: str, new_agent_price: float) -> Tuple[bool, str]:
        try:
            origin = self.config.ejfl.find_one({'nowuid': product_nowuid})
            if not origin:
                return False, "原始商品不存在"
            
            # ✅ 获取实时总部价格
            op = float(origin.get('money', 0))
            
            # ✅ 计算新的加价标记
            new_markup = round(new_agent_price - op, 2)
            
            if new_markup < 0:
                return False, f"代理价格不能低于总部价格 {op} USDT（当前总部价），您输入的 {new_agent_price} USDT 低于总部价"
            
            # ✅ 保存加价标记而不是固定代理价
            res = self.config.agent_product_prices.update_one(
                {'agent_bot_id': self.config.AGENT_BOT_ID, 'original_nowuid': product_nowuid},
                {'$set': {
                    'agent_markup': new_markup,
                    'updated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'manual_updated': True
                }}
            )
            if res.modified_count:
                profit_rate = (new_markup / op * 100) if op else 0
                return True, f"价格更新成功！加价 {new_markup:.2f}U，利润率 {profit_rate:.1f}%（基于当前总部价 {op}U）"
            return False, "无变化"
        except Exception as e:
            logger.error(f"❌ 更新代理价格失败: {e}")
            return False, f"失败: {e}"

    def toggle_product_status(self, product_nowuid: str) -> Tuple[bool, str]:
        try:
            cur = self.config.agent_product_prices.find_one({
                'agent_bot_id': self.config.AGENT_BOT_ID,
                'original_nowuid': product_nowuid
            })
            if not cur:
                return False, "商品不存在"
            new_status = not cur.get('is_active', True)
            self.config.agent_product_prices.update_one(
                {'agent_bot_id': self.config.AGENT_BOT_ID, 'original_nowuid': product_nowuid},
                {'$set': {'is_active': new_status, 'updated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}
            )
            return True, ("商品已启用" if new_status else "商品已禁用")
        except Exception as e:
            logger.error(f"❌ 切换状态失败: {e}")
            return False, f"失败: {e}"

    # ---------- 利润账户 ----------
    def update_profit_account(self, profit_delta: float):
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            acc = self.config.agent_profit_account.find_one({'agent_bot_id': self.config.AGENT_BOT_ID})
            if not acc:
                self.config.agent_profit_account.insert_one({
                    'agent_bot_id': self.config.AGENT_BOT_ID,
                    'total_profit': round(profit_delta, 6),
                    'withdrawn_profit': 0.0,
                    'created_time': now,
                    'updated_time': now
                })
            else:
                self.config.agent_profit_account.update_one(
                    {'agent_bot_id': self.config.AGENT_BOT_ID},
                    {'$inc': {'total_profit': round(profit_delta, 6)},
                     '$set': {'updated_time': now}}
                )
        except Exception as e:
            logger.error(f"❌ 更新利润账户失败: {e}")

    def get_profit_summary(self) -> Dict:
        try:
            acc = self.config.agent_profit_account.find_one({'agent_bot_id': self.config.AGENT_BOT_ID}) or {}
            total_profit = float(acc.get('total_profit', 0.0))
            q_base = {
                'agent_bot_id': self.config.AGENT_BOT_ID,
                'apply_role': 'agent',
                'type': 'agent_profit_withdrawal'
            }
            coll = self.config.withdrawal_requests

            def sum_status(st: str):
                return sum([float(x.get('amount', 0)) for x in coll.find({**q_base, 'status': st})])

            pending_amount = sum_status('pending')
            approved_amount = sum_status('approved')
            completed_amount = sum_status('completed')
            rejected_amount = sum_status('rejected')

            available_profit = total_profit - completed_amount - pending_amount - approved_amount
            if available_profit < 0:
                available_profit = 0.0

            if float(acc.get('withdrawn_profit', 0)) != completed_amount:
                self.config.agent_profit_account.update_one(
                    {'agent_bot_id': self.config.AGENT_BOT_ID},
                    {'$set': {'withdrawn_profit': round(completed_amount, 6),
                              'updated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}},
                    upsert=True
                )

            return {
                'total_profit': round(total_profit, 6),
                'withdrawn_profit': round(completed_amount, 6),
                'pending_profit': round(pending_amount, 6),
                'approved_unpaid_profit': round(approved_amount, 6),
                'rejected_profit': round(rejected_amount, 6),
                'available_profit': round(available_profit, 6),
                'request_count_pending': coll.count_documents({**q_base, 'status': 'pending'}),
                'request_count_approved': coll.count_documents({**q_base, 'status': 'approved'}),
                'updated_time': acc.get('updated_time')
            }
        except Exception as e:
            logger.error(f"❌ 获取利润汇总失败: {e}")
            return {
                'total_profit': 0.0, 'withdrawn_profit': 0.0,
                'pending_profit': 0.0, 'approved_unpaid_profit': 0.0,
                'rejected_profit': 0.0, 'available_profit': 0.0,
                'request_count_pending': 0, 'request_count_approved': 0,
                'updated_time': None
            }

    def request_profit_withdrawal(self, user_id: int, amount: float, withdrawal_address: str) -> Tuple[bool, str]:
        try:
            if user_id not in ADMIN_USERS:
                return False, "无权限"
            if amount <= 0:
                return False, "金额需大于0"
            summary = self.get_profit_summary()
            if amount > summary['available_profit']:
                return False, f"超过可提现余额 {summary['available_profit']:.2f} USDT"

            now = datetime.now()
            doc = {
                'agent_bot_id': self.config.AGENT_BOT_ID,
                'user_id': user_id,
                'amount': round(amount, 6),
                'withdrawal_address': withdrawal_address,
                'status': 'pending',
                'created_time': now,
                'updated_time': now,
                'apply_role': 'agent',
                'type': 'agent_profit_withdrawal',
                'profit_snapshot': summary['available_profit']
            }
            self.config.withdrawal_requests.insert_one(doc)

            if self.config.AGENT_NOTIFY_CHAT_ID:  # ✅ 正确
                try:
                    Bot(self.config.BOT_TOKEN).send_message(
                        chat_id=AGENT_NOTIFY_CHAT_ID,
                        text=(f"📢 <b>代理提现申请</b>\n\n"
                              f"🏢 代理ID：<code>{self._h(self.config.AGENT_BOT_ID)}</code>\n"
                              f"👤 用户：{self._link_user(user_id)}\n"
                              f"💰 金额：<b>{amount:.2f} USDT</b>\n"
                              f"🏦 地址：<code>{self._h(withdrawal_address)}</code>\n"
                              f"⏰ 时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as ne:
                    logger.warning(f"总部通知发送失败: {ne}")

            return True, "提现申请已提交，等待审核"
        except Exception as e:
            logger.error(f"❌ 提交提现失败: {e}")
            return False, "系统异常"

    # ---------- 充值创建 ----------
    def _gen_unique_suffix(self, digits: int = 4) -> int:
        return random.randint(1, 10**digits - 1)

    def _compose_expected_amount(self, base_amount: Decimal, suffix: int) -> Decimal:
        suffix_dec = Decimal(suffix) / Decimal(10**4)
        expected = (base_amount.quantize(Decimal("0.01")) + suffix_dec).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        return expected

    def create_recharge_order(self, user_id: int, base_amount: Decimal) -> Tuple[bool, str, Optional[Dict]]:
        try:
            if not self.config.AGENT_USDT_ADDRESS:
                return False, "系统地址未配置", None
            if base_amount < self.config.RECHARGE_MIN_USDT:
                return False, f"最低充值金额为 {self.config.RECHARGE_MIN_USDT} USDT", None

            for _ in range(5):
                code = self._gen_unique_suffix()
                expected_amount = self._compose_expected_amount(base_amount, code)
                exists = self.config.recharge_orders.find_one({
                    'agent_bot_id': self.config.AGENT_BOT_ID,
                    'status': {'$in': ['pending', 'created']},
                    'expected_amount': float(expected_amount),
                    'address': self.config.AGENT_USDT_ADDRESS
                })
                if not exists:
                    break
            else:
                return False, "系统繁忙，请稍后重试", None

            now = datetime.utcnow()
            expire_at = now + timedelta(minutes=self.config.RECHARGE_EXPIRE_MINUTES)
            order = {
                'agent_bot_id': self.config.AGENT_BOT_ID,
                'user_id': user_id,
                'network': 'TRON',
                'token': self.config.TOKEN_SYMBOL,
                'address': self.config.AGENT_USDT_ADDRESS,
                'base_amount': float(base_amount),
                'expected_amount': float(expected_amount),
                'unique_code': code,
                'status': 'pending',
                'created_time': now,
                'expire_time': expire_at,
                'paid_time': None,
                'tx_id': None,
                'from_address': None,
                'confirmations': 0
            }
            ins = self.config.recharge_orders.insert_one(order)
            order['_id'] = ins.inserted_id
            return True, "创建成功", order
        except Exception as e:
            logger.error(f"❌ 创建充值订单失败: {e}")
            return False, "系统异常，请稍后再试", None

    # ---------- 纯二维码 + caption ----------
    def _build_plain_qr(self, order: Dict) -> Optional[BytesIO]:
        """生成仅包含地址的二维码"""
        if qrcode is None or Image is None:
            return None
        address = str(order.get('address') or '').strip()
        payload = address
        logger.info(f"[QR] encoding pure address: {payload}")
        qr = qrcode.QRCode(version=None, box_size=10, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        pad = 40
        W = img.size[0] + pad * 2
        H = img.size[1] + pad * 2
        canvas = Image.new("RGB", (W, H), (255, 255, 255))
        canvas.paste(img, (pad, pad))
        bio = BytesIO()
        canvas.save(bio, format="PNG")
        bio.seek(0)
        return bio

    def _send_recharge_text_fallback(self, chat_id: int, order: Dict, reply_markup: InlineKeyboardMarkup):
        expected_amt = Decimal(str(order['expected_amount'])).quantize(Decimal("0.0001"))
        base_amt = Decimal(str(order['base_amount'])).quantize(Decimal("0.01"))
        expire_bj = self._to_beijing(order.get('expire_time')).strftime('%Y-%m-%d %H:%M')
        text = (
            "💰 余额充值（自动到账）\n\n"
            f"网络: TRON-TRC20\n"
            f"代币: {self._h(self.config.TOKEN_SYMBOL)}\n"
            f"收款地址: <code>{self._h(order['address'])}</code>\n\n"
            "请按以下“识别金额”精确转账:\n"
            f"应付金额: <b>{expected_amt}</b> USDT\n"
            f"基础金额: {base_amt} USDT\n"
            f"识别码: {order['unique_code']}\n\n"
            f"有效期至: {expire_bj} （10分钟内未支付该订单失效）\n\n"
            "注意:\n"
            "• 必须精确到 4 位小数的“应付金额”\n"
            "• 系统自动监听入账，无需手动校验"
        )
        Bot(self.config.BOT_TOKEN).send_message(
            chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )

    def send_plain_qr_with_caption(self, chat_id: int, order: Dict, reply_markup: InlineKeyboardMarkup):
        try:
            bio = self._build_plain_qr(order)
            expected_amt = Decimal(str(order['expected_amount'])).quantize(Decimal("0.0001"))
            base_amt = Decimal(str(order['base_amount'])).quantize(Decimal("0.01"))
            expire_bj = self._to_beijing(order.get('expire_time')).strftime('%Y-%m-%d %H:%M')
            caption = (
                "💰 <b>余额充值（自动到账）</b>\n\n"
                f"网络: TRON-TRC20\n"
                f"代币: {self._h(self.config.TOKEN_SYMBOL)}\n"
                f"收款地址: <code>{self._h(order['address'])}</code>\n\n"
                "请按以下“识别金额”精确转账:\n"
                f"应付金额: <b>{expected_amt}</b> USDT\n"
                f"基础金额: {base_amt} USDT\n"
                f"识别码: {order['unique_code']}\n\n"
                f"有效期至: {expire_bj} （10分钟内未支付该订单失效）\n\n"
                "注意:\n"
                "• 必须精确到 4 位小数的“应付金额”\n"
                "• 系统自动监听入账，无需手动校验"
            )
            if bio:
                Bot(self.config.BOT_TOKEN).send_photo(
                    chat_id=chat_id,
                    photo=bio,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            else:
                self._send_recharge_text_fallback(chat_id, order, reply_markup)
        except Exception as e:
            logger.warning(f"发送二维码caption失败: {e}")
            self._send_recharge_text_fallback(chat_id, order, reply_markup)

    # ---------- Tron 交易抓取与解析 ----------
    def _fetch_tronscan_transfers(self, to_address: str, limit: int = 50) -> List[Dict]:
        try:
            bases = [
                self.config.TRONSCAN_TRX20_API,
                "https://apilist.tronscanapi.com/api/token_trc20/transfers",
                "https://apilist.tronscan.org/api/token_trc20/transfers",
            ]
            tried = set()
            for base in bases:
                if not base or base in tried:
                    continue
                tried.add(base)
                params = {
                    "toAddress": to_address,
                    "contract": self.config.USDT_TRON_CONTRACT,
                    "contract_address": self.config.USDT_TRON_CONTRACT,
                    "limit": min(int(limit), 200),
                    "sort": "-timestamp",
                }
                try:
                    r = requests.get(base, params=params, timeout=10)
                    if r.status_code != 200:
                        logger.warning(f"TronScan API 非 200: {r.status_code} url={base}")
                        continue
                    data = r.json() or {}
                    items = data.get("token_transfers") or data.get("data") or []
                    return items
                except Exception as ie:
                    logger.warning(f"TronScan 调用异常 url={base}: {ie}")
                    continue
            return []
        except Exception as e:
            logger.warning(f"TronScan API 调用失败: {e}")
            return []

    def _fetch_trongrid_trc20_transfers(self, to_address: str, limit: int = 50) -> List[Dict]:
        try:
            base = self.config.TRONGRID_API_BASE
            url = f"{base}/v1/accounts/{to_address}/transactions/trc20"
            params = {
                "limit": min(int(limit), 200),
                "contract_address": self.config.USDT_TRON_CONTRACT
            }
            attempts = max(len(self.config.TRON_API_KEYS), 1)
            last_err = None
            for _ in range(attempts):
                headers = {}
                api_key = self.config._next_tron_api_key()
                if api_key:
                    headers[self.config.TRON_API_KEY_HEADER] = api_key
                try:
                    r = requests.get(url, params=params, headers=headers, timeout=10)
                    if r.status_code != 200:
                        last_err = f"HTTP {r.status_code}"
                        if r.status_code in (429, 500, 502, 503, 504):
                            continue
                        return []
                    data = r.json() or {}
                    items = data.get("data") or []
                    norm = []
                    for it in items:
                        to_addr = (it.get("to") or "").lower()
                        if to_addr != to_address.lower():
                            continue
                        token_info = it.get("token_info") or {}
                        dec = int(token_info.get("decimals") or 6)
                        raw_val = it.get("value")
                        amount_str = None
                        if raw_val is not None:
                            try:
                                amount_str = (Decimal(str(raw_val)) / Decimal(10 ** dec)).quantize(Decimal("0.0001"))
                            except Exception:
                                amount_str = None
                        norm.append({
                            "to_address": it.get("to"),
                            "from_address": it.get("from"),
                            "amount_str": str(amount_str) if amount_str is not None else None,
                            "block_ts": it.get("block_timestamp"),
                            "transaction_id": it.get("transaction_id"),
                            "tokenInfo": {"tokenDecimal": dec}
                        })
                    return norm
                except Exception as e:
                    last_err = str(e)
                    continue
            if last_err:
                logger.warning(f"TronGrid 查询失败（已轮换密钥）：{last_err}")
            return []
        except Exception as e:
            logger.warning(f"TronGrid API 异常: {e}")
            return []

    def _fetch_token_transfers(self, to_address: str, limit: int = 50) -> List[Dict]:
        items = []
        if getattr(self.config, "TRON_API_KEYS", None):
            items = self._fetch_trongrid_trc20_transfers(to_address, limit)
        if not items:
            items = self._fetch_tronscan_transfers(to_address, limit)
        return items

    def _parse_amount(self, it) -> Optional[Decimal]:
        try:
            if it.get("amount_str") is not None:
                return Decimal(str(it["amount_str"])).quantize(Decimal("0.0001"))
            token_info = it.get("tokenInfo") or it.get("token_info") or {}
            dec_raw = token_info.get("tokenDecimal") or token_info.get("decimals") or it.get("tokenDecimal")
            try:
                decimals = int(dec_raw) if dec_raw is not None else 6
            except Exception:
                decimals = 6
            for key in ("value", "amount", "quant", "value_str", "amount_value", "amountValue"):
                if it.get(key) is not None:
                    v = it.get(key)
                    dv = Decimal(str(v))
                    if (isinstance(v, int) or (isinstance(v, str) and v.isdigit())) and len(str(v)) > 12:
                        dv = dv / Decimal(10 ** decimals)
                    return dv.quantize(Decimal("0.0001"))
            return None
        except Exception:
            return None

    # ---------- 充值校验 / 入账 / 轮询 ----------
    def verify_recharge_order(self, order: Dict) -> Tuple[bool, str]:
        try:
            if order.get('status') != 'pending':
                return False, "订单状态不可校验"
            if datetime.utcnow() > order.get('expire_time', datetime.utcnow()):
                self.config.recharge_orders.update_one({'_id': order['_id']}, {'$set': {'status': 'expired'}})
                return False, "订单已过期"

            expected = Decimal(str(order['expected_amount'])).quantize(Decimal("0.0001"))
            address = order['address']
            transfers = self._fetch_token_transfers(address, limit=100)
            if not transfers:
                return False, "未查询到转账记录"

            created_ts = order['created_time']
            for it in transfers:
                to_addr = (it.get('to_address') or it.get('to') or it.get('transferToAddress') or '').lower()
                amt = self._parse_amount(it)
                ts_ms = it.get('block_ts') or it.get('timestamp') or 0
                tx_time = datetime.utcfromtimestamp(int(ts_ms) / 1000) if ts_ms else None
                if to_addr != address.lower():
                    continue
                if amt is None or amt != expected:
                    continue
                if not tx_time or tx_time < created_ts - timedelta(minutes=5):
                    continue
                tx_id = it.get('transaction_id') or it.get('hash') or it.get('txHash') or ''
                from_addr = it.get('from_address') or it.get('from') or ''
                self._settle_recharge(order, tx_id, from_addr, tx_time)
                return True, "充值成功自动入账"
            return False, "暂未匹配到您的转账"
        except Exception as e:
            logger.error(f"❌ 校验充值失败: {e}")
            return False, "校验异常，请稍后重试"

    def _settle_recharge(self, order: Dict, tx_id: str, from_addr: str, paid_time: datetime):
        try:
            self.config.recharge_orders.update_one(
                {'_id': order['_id'], 'status': 'pending'},
                {'$set': {
                    'status': 'paid',
                    'tx_id': tx_id,
                    'from_address': from_addr,
                    'paid_time': paid_time
                }}
            )
            amt = float(order['base_amount'])
            self.config.get_agent_user_collection().update_one(
                {'user_id': order['user_id']},
                {'$inc': {'USDT': amt},
                 '$set': {'last_active': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}
            )
            user_doc = self.config.get_agent_user_collection().find_one(
                {'user_id': order['user_id']}, {'USDT': 1}
            )
            new_balance = float(user_doc.get('USDT', 0.0)) if user_doc else 0.0

            # 用户通知
            try:
                bot = Bot(self.config.BOT_TOKEN)
                friendly_time = self._to_beijing(paid_time).strftime('%Y-%m-%d %H:%M:%S')
                tx_short = (tx_id[:12] + '...') if tx_id and len(tx_id) > 12 else (tx_id or '-')
                msg = (
                    "🎉 恭喜您，充值成功！\n"
                    f"充值金额：{amt:.2f} {self.config.TOKEN_SYMBOL}\n"
                    f"当前余额：{new_balance:.2f} {self.config.TOKEN_SYMBOL}\n"
                    f"当前时间：{friendly_time}\n"
                    f"交易：{tx_short}\n\n"
                    "🔥祝您生意兴隆，财源广进！"
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛍️ 商品中心", callback_data="products"),
                     InlineKeyboardButton("👤 个人中心", callback_data="profile")],
                    [InlineKeyboardButton("📜 充值记录", callback_data="recharge_list")]
                ])
                bot.send_message(chat_id=order['user_id'], text=msg, reply_markup=kb)
            except Exception as ue:
                logger.warning(f"用户充值成功通知发送失败: {ue}")

            # 群通知
            if self.config.AGENT_NOTIFY_CHAT_ID:  # ✅ 正确
                try:
                    tx_short = (tx_id[:12] + '...') if tx_id and len(tx_id) > 12 else (tx_id or '-')
                    text = (
                        "✅ <b>充值入账</b>\n\n"
                        f"🏢 代理ID：<code>{self._h(self.config.AGENT_BOT_ID)}</code>\n"
                        f"👤 用户：{self._link_user(order['user_id'])}\n"
                        f"💰 金额：<b>{amt:.2f} {self._h(self.config.TOKEN_SYMBOL)}</b>\n"
                        f"🏦 收款地址：<code>{self._h(self.config.AGENT_USDT_ADDRESS)}</code>\n"
                        f"🔗 TX：<code>{self._h(tx_short)}</code>"
                    )
                    Bot(self.config.BOT_TOKEN).send_message(
                        chat_id=AGENT_NOTIFY_CHAT_ID,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._kb_tx_addr_user(tx_id, self.config.AGENT_USDT_ADDRESS, order['user_id'])
                    )
                except Exception as ne:
                    logger.warning(f"总部通知发送失败: {ne}")
        except Exception as e:
            logger.error(f"❌ 入账失败: {e}")

    def poll_and_auto_settle_recharges(self, max_orders: int = 80):
        try:
            now = datetime.utcnow()
            q = {
                'agent_bot_id': self.config.AGENT_BOT_ID,
                'status': 'pending',
                'expire_time': {'$gte': now}
            }
            orders = list(self.config.recharge_orders.find(q).sort('created_time', -1).limit(max_orders))
            for od in orders:
                ok, _ = self.verify_recharge_order(od)
                if ok:
                    logger.info(f"充值自动入账成功 order={od.get('_id')}")
        except Exception as e:
            logger.warning(f"自动轮询充值异常: {e}")

    def list_recharges(self, user_id: int, limit: int = 10, include_canceled: bool = False) -> List[Dict]:
        try:
            q = {'agent_bot_id': self.config.AGENT_BOT_ID, 'user_id': user_id}
            if not include_canceled:
                q['status'] = {'$ne': 'canceled'}
            return list(self.config.recharge_orders.find(q).sort('created_time', -1).limit(limit))
        except Exception as e:
            logger.error(f"❌ 查询充值记录失败: {e}")
            return []

    def send_batch_files_to_user(self, user_id: int, items: List[Dict], product_name: str, order_id: str = "") -> int:
        logger.info(f"开始打包发送: {product_name} items={len(items)}")
        try:
            if not items:
                return 0
            bot = Bot(self.config.BOT_TOKEN)
            first = items[0]
            item_type = first.get('leixing', '')
            nowuid = first.get('nowuid', '')
            if item_type == '协议号':
                base_dir = f"{self.config.FILE_BASE_PATH}/协议号/{nowuid}"
            else:
                base_dir = f"{self.config.FILE_BASE_PATH}/{item_type}/{nowuid}"
            if not os.path.exists(base_dir):
                return 0
            delivery_dir = f"{self.config.FILE_BASE_PATH}/协议号发货"
            os.makedirs(delivery_dir, exist_ok=True)
            
            # ✅ 改成：日期_用户ID_订单号后4位.zip
            from datetime import datetime
            date_str = datetime.now().strftime("%Y%m%d")
            short_order_id = order_id[-4:] if order_id else "0000"
            zip_filename = f"{date_str}_{user_id}_{short_order_id}.zip"
            zip_path = f"{delivery_dir}/{zip_filename}"
            
            files_added = 0
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    if item_type == '协议号':
                        for it in items:
                            pname = it.get('projectname', '')
                            jf = os.path.join(base_dir, f"{pname}.json")
                            sf = os.path.join(base_dir, f"{pname}.session")
                            if os.path.exists(jf):
                                zf.write(jf, f"{pname}.json"); files_added += 1
                            if os.path.exists(sf):
                                zf.write(sf, f"{pname}.session"); files_added += 1
                        for fn in os.listdir(base_dir):
                            if fn.lower().endswith(('.txt', '.md')) and files_added < 500:
                                fp = os.path.join(base_dir, fn)
                                if os.path.isfile(fp):
                                    zf.write(fp, fn); files_added += 1
                    else:
                        for idx, _ in enumerate(items, 1):
                            for fn in os.listdir(base_dir):
                                fp = os.path.join(base_dir, fn)
                                if os.path.isfile(fp):
                                    zf.write(fp, f"{idx:02d}_{fn}")
                                    files_added += 1
                if files_added == 0:
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                    return 0
                if os.path.getsize(zip_path) > 50 * 1024 * 1024:
                    os.remove(zip_path)
                    return 0
                with open(zip_path, 'rb') as f:
                    bot.send_document(
                        chat_id=user_id,
                        document=f,
                        caption=(f"📁 <b>{self._h(product_name)}</b>\n"
                                 f"📦 批量发货文件包\n"
                                 f"🔢 商品数量: {len(items)} 个\n"
                                 f"📂 文件总数: {files_added} 个\n"
                                 f"⏰ 发货时间: {self._to_beijing(datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S')}"),
                        parse_mode=ParseMode.HTML
                    )
                try:
                    os.remove(zip_path)
                except:
                    pass
                return 1
            except Exception as e:
                logger.error(f"打包失败: {e}")
                try:
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                except:
                    pass
                return 0
        except Exception as e:
            logger.error(f"批量发送失败: {e}")
            return 0

    # ---------- 购买流程 ----------
    def process_purchase(self, user_id: int, product_nowuid: str, quantity: int = 1) -> Tuple[bool, Any]:
        try:
            coll_users = self.config.get_agent_user_collection()
            user = coll_users.find_one({'user_id': user_id})
            if not user:
                return False, "用户不存在"

            # ✅ 获取商品原始信息
            product = self.config.ejfl.find_one({'nowuid': product_nowuid})
            if not product:
                return False, "原始商品不存在"

            # ✅ 获取代理价格配置
            price_cfg = self.config.agent_product_prices.find_one({
                'agent_bot_id': self.config.AGENT_BOT_ID,
                'original_nowuid': product_nowuid,
                'is_active': True
            })
            if not price_cfg:
                return False, "商品不存在或已下架"

            # ✅ 获取库存
            items = list(self.config.hb.find({'nowuid': product_nowuid, 'state': 0}).limit(quantity))
            if len(items) < quantity:
                return False, "库存不足"

            # ✅ 实时计算代理价格
            origin_price = float(product.get('money', 0))
            agent_markup = float(price_cfg.get('agent_markup', 0))
            agent_price = round(origin_price + agent_markup, 2)

            total_cost = agent_price * quantity
            balance = float(user.get('USDT', 0))

            if balance < total_cost:
                return False, "余额不足"

            new_balance = balance - total_cost
            coll_users.update_one(
                {'user_id': user_id},
                {'$set': {'USDT': new_balance, 'last_active': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                 '$inc': {'zgje': total_cost, 'zgsl': quantity}}
            )

            ids = [i['_id'] for i in items]
            sale_time = self._to_beijing(datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S')
            self.config.hb.update_many(
                {'_id': {'$in': ids}},
                {'$set': {'state': 1, 'sale_time': sale_time, 'yssj': sale_time, 'gmid': user_id}}
            )

            # ✅ 订单号先生成
            order_id = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{user_id}"

            files_sent = 0
            try:
                # ✅ 发货函数传递订单号当作第4参数
                files_sent = self.send_batch_files_to_user(user_id, items, product.get('projectname', ''), order_id)
            except Exception as fe:
                logger.warning(f"发货文件异常: {fe}")

            # ✅ 计算利润
            profit_unit = max(agent_markup, 0)
            total_profit = profit_unit * quantity
            if total_profit > 0:
                self.update_profit_account(total_profit)

            order_coll = self.config.get_agent_gmjlu_collection()
            order_coll.insert_one({
                'leixing': 'purchase',
                'bianhao': order_id,
                'user_id': user_id,
                'projectname': product.get('projectname', ''),
                'text': str(ids[0]) if ids else '',
                'ts': total_cost,
                'timer': sale_time,
                'count': quantity,
                'agent_bot_id': self.config.AGENT_BOT_ID,
                'original_price': origin_price,
                'agent_price': agent_price,
                'profit_per_unit': profit_unit,
                'total_profit': total_profit
            })

            # 群通知
            try:
                if self.config.AGENT_NOTIFY_CHAT_ID:
                    p_name = self._h(product.get('projectname', ''))
                    nowuid = product.get('nowuid', '')
                    text = (
                        "🛒 <b>用户购买</b>\n\n"
                        f"🏢 代理ID：<code>{self._h(self.config.AGENT_BOT_ID)}</code>\n"
                        f"👤 用户：{self._link_user(user_id)}\n"
                        f"📦 商品：<b>{p_name}</b>\n"
                        f"🔢 数量：<b>{quantity}</b>\n"
                        f"💴 单价：<b>{agent_price:.2f}U</b>\n"
                        f"💰 总额：<b>{total_cost:.2f}U</b>\n"
                        f"📈 利润：<b>{total_profit:.2f}U</b>\n"
                        f"🧾 订单号：<code>{self._h(order_id)}</code>\n"
                        f"⏰ 时间：{self._h(sale_time)}"
                    )
                    Bot(self.config.BOT_TOKEN).send_message(
                        chat_id=AGENT_NOTIFY_CHAT_ID,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._kb_product_actions(nowuid, user_id)
                    )
            except Exception as ne:
                logger.warning(f"购买群通知发送失败: {ne}")

            return True, {
                'order_id': order_id,
                'product_name': product.get('projectname', ''),
                'quantity': quantity,
                'total_cost': total_cost,
                'user_balance': new_balance,
                'files_sent': files_sent,
                'total_profit': total_profit
            }
        except Exception as e:
            logger.error(f"处理购买失败: {e}")
            return False, f"购买处理异常: {e}"
            
    # ---------- 统计 ----------
    def get_sales_statistics(self, days: int = 30) -> Dict:
        try:
            end = datetime.now(); start = end - timedelta(days=days)
            s_str = start.strftime('%Y-%m-%d %H:%M:%S')
            e_str = end.strftime('%Y-%m-%d %H:%M:%S')
            coll = self.config.get_agent_gmjlu_collection()
            base = list(coll.aggregate([
                {'$match': {'leixing': 'purchase', 'timer': {'$gte': s_str, '$lte': e_str}}},
                {'$group': {'_id': None, 'total_orders': {'$sum': 1},
                            'total_revenue': {'$sum': '$ts'}, 'total_quantity': {'$sum': '$count'}}}
            ]))
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
            today = list(coll.aggregate([
                {'$match': {'leixing': 'purchase', 'timer': {'$gte': today_start}}},
                {'$group': {'_id': None, 'today_orders': {'$sum': 1},
                            'today_revenue': {'$sum': '$ts'}, 'today_quantity': {'$sum': '$count'}}}
            ]))
            popular = list(coll.aggregate([
                {'$match': {'leixing': 'purchase', 'timer': {'$gte': s_str, '$lte': e_str}}},
                {'$group': {'_id': '$projectname', 'total_sold': {'$sum': '$count'},
                            'total_revenue': {'$sum': '$ts'}, 'order_count': {'$sum': 1}}},
                {'$sort': {'total_sold': -1}},
                {'$limit': 5}
            ]))
            result = {
                'period_days': days,
                'total_orders': base[0]['total_orders'] if base else 0,
                'total_revenue': base[0]['total_revenue'] if base else 0.0,
                'total_quantity': base[0]['total_quantity'] if base else 0,
                'today_orders': today[0]['today_orders'] if today else 0,
                'today_revenue': today[0]['today_revenue'] if today else 0.0,
                'today_quantity': today[0]['today_quantity'] if today else 0,
                'popular_products': popular,
                'avg_order_value': round((base[0]['total_revenue'] / max(base[0]['total_orders'], 1)), 2) if base else 0.0
            }
            return result
        except Exception as e:
            logger.error(f"❌ 销售统计失败: {e}")
            return {
                'period_days': days, 'total_orders': 0, 'total_revenue': 0.0, 'total_quantity': 0,
                'today_orders': 0, 'today_revenue': 0.0, 'today_quantity': 0,
                'popular_products': [], 'avg_order_value': 0.0
            }

    def get_user_statistics(self) -> Dict:
        try:
            users = self.config.get_agent_user_collection()
            total = users.count_documents({})
            active_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            active = users.count_documents({'last_active': {'$gte': active_date}})
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
            today_new = users.count_documents({'register_time': {'$gte': today_start}})
            bal_data = list(users.aggregate([{'$group': {
                '_id': None, 'total_balance': {'$sum': '$USDT'},
                'avg_balance': {'$avg': '$USDT'}, 'total_spent': {'$sum': '$zgje'}
            }}]))
            spending_levels = {
                'bronze': users.count_documents({'zgje': {'$lt': 50}}),
                'silver': users.count_documents({'zgje': {'$gte': 50, '$lt': 100}}),
                'gold': users.count_documents({'zgje': {'$gte': 100}})
            }
            return {
                'total_users': total,
                'active_users': active,
                'today_new_users': today_new,
                'total_balance': bal_data[0]['total_balance'] if bal_data else 0.0,
                'avg_balance': round(bal_data[0]['avg_balance'], 2) if bal_data else 0.0,
                'total_spent': bal_data[0]['total_spent'] if bal_data else 0.0,
                'spending_levels': spending_levels,
                'activity_rate': round((active / max(total, 1)) * 100, 1)
            }
        except Exception as e:
            logger.error(f"❌ 用户统计失败: {e}")
            return {
                'total_users': 0, 'active_users': 0, 'today_new_users': 0,
                'total_balance': 0.0, 'avg_balance': 0.0, 'total_spent': 0.0,
                'spending_levels': {'bronze': 0, 'silver': 0, 'gold': 0}, 'activity_rate': 0.0
            }

    def get_product_statistics(self) -> Dict:
        try:
            total = self.config.agent_product_prices.count_documents({'agent_bot_id': self.config.AGENT_BOT_ID})
            active = self.config.agent_product_prices.count_documents({'agent_bot_id': self.config.AGENT_BOT_ID, 'is_active': True})
            stock_pipeline = [
                {'$match': {'state': 0}},
                {'$group': {'_id': '$leixing', 'stock_count': {'$sum': 1}}},
                {'$sort': {'stock_count': -1}}
            ]
            stock_by_category = list(self.config.hb.aggregate(stock_pipeline))
            total_stock = self.config.hb.count_documents({'state': 0})
            sold_stock = self.config.hb.count_documents({'state': 1})
            price_stats = list(self.config.agent_product_prices.aggregate([
                {'$match': {'agent_bot_id': self.config.AGENT_BOT_ID}},
                {'$group': {'_id': None, 'avg_profit_rate': {'$avg': '$profit_rate'},
                            'highest_profit_rate': {'$max': '$profit_rate'},
                            'lowest_profit_rate': {'$min': '$profit_rate'}}}
            ]))
            return {
                'total_products': total,
                'active_products': active,
                'inactive_products': total - active,
                'total_stock': total_stock,
                'sold_stock': sold_stock,
                'stock_by_category': stock_by_category,
                'avg_profit_rate': round(price_stats[0]['avg_profit_rate'], 1) if price_stats else 0.0,
                'highest_profit_rate': round(price_stats[0]['highest_profit_rate'], 1) if price_stats else 0.0,
                'lowest_profit_rate': round(price_stats[0]['lowest_profit_rate'], 1) if price_stats else 0.0,
                'stock_turnover_rate': round((sold_stock / max(sold_stock + total_stock, 1)) * 100, 1)
            }
        except Exception as e:
            logger.error(f"❌ 商品统计失败: {e}")
            return {
                'total_products': 0, 'active_products': 0, 'inactive_products': 0,
                'total_stock': 0, 'sold_stock': 0, 'stock_by_category': [],
                'avg_profit_rate': 0.0, 'highest_profit_rate': 0.0,
                'lowest_profit_rate': 0.0, 'stock_turnover_rate': 0.0
            }

    def get_financial_statistics(self, days: int = 30) -> Dict:
        try:
            end = datetime.now(); start = end - timedelta(days=days)
            s_str = start.strftime('%Y-%m-%d %H:%M:%S')
            coll = self.config.get_agent_gmjlu_collection()
            revenue = list(coll.aggregate([
                {'$match': {'leixing': 'purchase', 'timer': {'$gte': s_str}}},
                {'$group': {'_id': None, 'total_revenue': {'$sum': '$ts'}, 'order_count': {'$sum': 1}}}
            ]))
            trends = list(coll.aggregate([
                {'$match': {'leixing': 'purchase', 'timer': {'$gte': (end - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')}}},
                {'$addFields': {'date_only': {'$substr': ['$timer', 0, 10]}}},
                {'$group': {'_id': '$date_only', 'daily_revenue': {'$sum': '$ts'}, 'daily_orders': {'$sum': 1}}},
                {'$sort': {'_id': 1}}
            ]))
            total_rev = revenue[0]['total_revenue'] if revenue else 0.0
            order_cnt = revenue[0]['order_count'] if revenue else 0
            return {
                'period_days': days,
                'total_revenue': total_rev,
                'estimated_profit': total_rev * 0.2,
                'profit_margin': 20.0,
                'order_count': order_cnt,
                'avg_order_value': round(total_rev / max(order_cnt, 1), 2),
                'daily_trends': trends,
                'revenue_growth': 0.0
            }
        except Exception as e:
            logger.error(f"❌ 财务统计失败: {e}")
            return {
                'period_days': days, 'total_revenue': 0.0, 'estimated_profit': 0.0,
                'profit_margin': 0.0, 'order_count': 0, 'avg_order_value': 0.0,
                'daily_trends': [], 'revenue_growth': 0.0
            }


class AgentBotHandlers:
    """按钮与消息处理"""

    def __init__(self, core: AgentBotCore):
        self.core = core
        self.user_states: Dict[int, Dict[str, Any]] = {}

    def H(self, s: Any) -> str:
        try:
            return html_escape(str(s) if s is not None else "", quote=False)
        except Exception:
            return str(s or "")


    def safe_edit_message(self, query, text, keyboard, parse_mode=ParseMode.HTML):
        markup, is_photo = None, False
        try:
            # 将普通二维数组按钮转为 InlineKeyboardMarkup
            markup = keyboard if isinstance(keyboard, InlineKeyboardMarkup) else InlineKeyboardMarkup(keyboard)

            # 图片消息（photo）没有 message.text，需要改用 edit_message_caption
            is_photo = bool(getattr(query.message, "photo", None)) and not getattr(query.message, "text", None)
            if is_photo:
                if len(text) > 1000:
                    text = text[:1000] + "..."
                query.edit_message_caption(caption=text, reply_markup=markup, parse_mode=parse_mode)
                return

            old_text = (getattr(query.message, "text", "") or "")
            if old_text.strip() == text.strip():
                try:
                    query.answer("界面已是最新状态")
                except:
                    pass
                return

            query.edit_message_text(text, reply_markup=markup, parse_mode=parse_mode)

        except Exception as e:
            msg = str(e)
            try:
                if "Message is not modified" in msg:
                    try:
                        query.answer("界面已是最新状态")
                    except:
                        pass
                elif "Can't parse entities" in msg or "can't parse entities" in msg:
                    # HTML 解析失败，回退纯文本
                    if is_photo:
                        query.edit_message_caption(caption=text, reply_markup=markup, parse_mode=None)
                    else:
                        query.edit_message_text(text, reply_markup=markup, parse_mode=None)
                    logger.warning(f"HTML解析失败，已回退纯文本发送: {e}")
                elif "There is no text in the message to edit" in msg or "no text in the message to edit" in msg:
                    # 照片消息/无法编辑文本，删除原消息并重发新文本
                    try:
                        chat_id = query.message.chat_id
                        query.message.delete()
                        Bot(self.core.config.BOT_TOKEN).send_message(
                            chat_id=chat_id, text=text, reply_markup=markup, parse_mode=parse_mode
                        )
                    except Exception as e_del:
                        logger.warning(f"回退删除重发失败: {e_del}")
                else:
                    logger.warning(f"⚠️ safe_edit_message 编辑失败: {e}")
                    try:
                        query.answer("刷新失败，请重试")
                    except:
                        pass
            except Exception:
                pass

    # ========== 命令 / 主菜单 ==========


    def start_command(self, update: Update, context: CallbackContext):
        user = update.effective_user
        # ✅ 启动时触发一次商品同步
        if user.id in ADMIN_USERS:
            synced = self.core.auto_sync_new_products()
            if synced > 0:
                logger.info(f"✅ 启动时同步了 {synced} 个新商品")
        
        if self.core.register_user(user.id, user.username or "", user.first_name or ""):
            text = f"""🎉 欢迎使用 {self.H(self.core.config.AGENT_NAME)}！

👤 用户信息
• ID: {user.id}
• 用户名: @{self.H(user.username or '未设置')}
• 昵称: {self.H(user.first_name or '未设置')}

请选择功能："""
            kb = [
                [InlineKeyboardButton("🛍️ 商品中心", callback_data="products"),
                 InlineKeyboardButton("👤 个人中心", callback_data="profile")],
                [InlineKeyboardButton("💰 充值余额", callback_data="recharge"),
                 InlineKeyboardButton("📊 订单历史", callback_data="orders")]
            ]
            if user.id in ADMIN_USERS:
                kb.append([InlineKeyboardButton("💰 价格管理", callback_data="price_management"),
                           InlineKeyboardButton("📊 系统报表", callback_data="system_reports")])
                kb.append([InlineKeyboardButton("💸 利润提现", callback_data="profit_center")])
            kb.append([InlineKeyboardButton("📞 联系客服", callback_data="support"),
                       InlineKeyboardButton("❓ 使用帮助", callback_data="help")])
            update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        else:
            update.message.reply_text("初始化失败，请稍后重试")

    def show_main_menu(self, query):
        user = query.from_user
        kb = [
            [InlineKeyboardButton("🛍️ 商品中心", callback_data="products"),
             InlineKeyboardButton("👤 个人中心", callback_data="profile")],
            [InlineKeyboardButton("💰 充值余额", callback_data="recharge"),
             InlineKeyboardButton("📊 订单历史", callback_data="orders")]
        ]
        if user.id in ADMIN_USERS:
            kb.append([InlineKeyboardButton("💰 价格管理", callback_data="price_management"),
                       InlineKeyboardButton("📊 系统报表", callback_data="system_reports")])
            kb.append([InlineKeyboardButton("💸 利润提现", callback_data="profit_center")])
        kb.append([InlineKeyboardButton("📞 联系客服", callback_data="support"),
                   InlineKeyboardButton("❓ 使用帮助", callback_data="help")])
        text = f"🏠 主菜单\n\n当前时间: {self.core._to_beijing(datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S')}"
        self.safe_edit_message(query, text, kb, parse_mode=None)

    # ========== 利润中心 / 提现 ==========
    def show_profit_center(self, query):
        uid = query.from_user.id
        if uid not in ADMIN_USERS:
            self.safe_edit_message(query, "❌ 无权限", [[InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]], parse_mode=None)
            return
        s = self.core.get_profit_summary()
        refresh_time = self.core._to_beijing(datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S')
        text = f"""💸 <b>利润中心</b>

累计利润: {s['total_profit']:.2f} USDT
已提现: {s['withdrawn_profit']:.2f} USDT
待审核: {s['pending_profit']:.2f} USDT
可提现: {s['available_profit']:.2f} USDT
待处理申请: {s['request_count_pending']} 笔


刷新时间: {refresh_time}

• 审核/付款需人工处理
"""
        kb = [
            [InlineKeyboardButton("📝 申请提现", callback_data="profit_withdraw"),
             InlineKeyboardButton("📋 申请记录", callback_data="profit_withdraw_list")],
            [InlineKeyboardButton("🔄 刷新", callback_data="profit_center"),
             InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]
        ]
        self.safe_edit_message(query, text, kb, parse_mode=ParseMode.HTML)

    def start_withdrawal(self, query):
        uid = query.from_user.id
        if uid not in ADMIN_USERS:
            query.answer("无权限", show_alert=True)
            return
        s = self.core.get_profit_summary()
        if s['available_profit'] <= 0:
            self.safe_edit_message(query, "⚠️ 当前无可提现利润", [[InlineKeyboardButton("🔙 返回", callback_data="profit_center")]], parse_mode=None)
            return
        text = f"""📝 <b>申请提现</b>

可提现金额: {s['available_profit']:.2f} USDT
请输入提现金额（例如: {min(s['available_profit'], 10):.2f}）

直接发送数字金额："""
        self.user_states[uid] = {'state': 'waiting_withdraw_amount'}
        self.safe_edit_message(query, text, [[InlineKeyboardButton("🔙 取消", callback_data="profit_center")]], parse_mode=ParseMode.HTML)

    def handle_withdraw_amount_input(self, update: Update):
        uid = update.effective_user.id
        text = update.message.text.strip()
        try:
            amt = float(text)
            s = self.core.get_profit_summary()
            if amt <= 0:
                update.message.reply_text("❌ 金额必须大于0，请重新输入")
                return
            if amt > s['available_profit']:
                update.message.reply_text(f"❌ 超出可提现余额 {s['available_profit']:.2f}，请重新输入")
                return
            self.user_states[uid] = {'state': 'waiting_withdraw_address', 'withdraw_amount': amt}
            update.message.reply_text(
                f"✅ 金额已记录：{amt:.2f} USDT\n请发送收款地址（TRON 或 ERC20）",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="profit_center")]])
            )
        except ValueError:
            update.message.reply_text("❌ 金额格式错误，请输入数字")

    def handle_withdraw_address_input(self, update: Update):
        uid = update.effective_user.id
        address = update.message.text.strip()
        if len(address) < 10:
            update.message.reply_text("❌ 地址长度不正确，请重新输入")
            return
        amt = self.user_states[uid]['withdraw_amount']
        ok, msg = self.core.request_profit_withdrawal(uid, amt, address)
        self.user_states.pop(uid, None)
        if ok:
            update.message.reply_text(
                f"✅ 提现申请成功\n金额：{amt:.2f} USDT\n地址：{self.H(address)}\n状态：待审核",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💸 返回利润中心", callback_data="profit_center")]]),
                parse_mode=ParseMode.HTML
            )
        else:
            update.message.reply_text(f"❌ {msg}")

    def show_withdrawal_list(self, query):
        uid = query.from_user.id
        if uid not in ADMIN_USERS:
            self.safe_edit_message(query, "❌ 无权限", [[InlineKeyboardButton("返回", callback_data="back_main")]], parse_mode=None)
            return
        recs = self.core.config.withdrawal_requests.find({
            'agent_bot_id': self.core.config.AGENT_BOT_ID,
            'apply_role': 'agent',
            'type': 'agent_profit_withdrawal'
        }).sort('created_time', -1).limit(30)
        recs = list(recs)
        if not recs:
            self.safe_edit_message(query, "📋 提现记录\n\n暂无申请", [[InlineKeyboardButton("🔙 返回", callback_data="profit_center")]], parse_mode=None)
            return
        text = "📋 提现记录（最新优先）\n\n"
        for r in recs:
            status = r.get('status')
            amount = r.get('amount', 0.0)
            created = r.get('created_time')
            created_s = self.core._to_beijing(created).strftime('%m-%d %H:%M') if created else '-'
            addr = str(r.get('withdrawal_address', ''))
            addr_short = f"{addr[:6]}...{addr[-6:]}" if len(addr) > 12 else addr
            text += f"💰 {amount:.4f}U | {status}\n地址: {self.H(addr_short)} | 时间(京): {self.H(created_s)}\n"
            if status == 'rejected' and r.get('reject_reason'):
                text += f"原因: {self.H(r.get('reject_reason'))}\n"
            if status == 'completed' and r.get('tx_hash'):
                th = str(r['tx_hash'])
                text += f"Tx: {self.H(th[:12] + '...' if len(th) > 12 else th)}\n"
            text += "\n"
        text += "（需人工审核/付款）"
        self.safe_edit_message(query, text, [[InlineKeyboardButton("🔙 返回", callback_data="profit_center")]], parse_mode=None)

    # ========== 商品相关 ==========
    def show_product_categories(self, query):
        """显示商品分类（一级分类）- 从fenlei表读取"""
        try:
            # ✅ 先自动同步新商品
            self.core.auto_sync_new_products()
            
            # ✅ 从 fenlei 表读分类
            fenlei_coll = self.core.config.db['fenlei']
            all_categories = list(fenlei_coll.find({}))
            
            if not all_categories:
                self.safe_edit_message(query, "❌ 暂无可用商品分类", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)
                return
            
            text = (
                "🛒 <b>商品分类 - 请选择所需商品：</b>\n\n"
                "「快送商品区」-「热选择所需商品」\n\n"
                "<b>❗️首次购买请先少量测试，避免纠纷</b>！\n\n"
                "<b>❗️长期未使用账户可能会出现问题，联系客服处理</b>。"
            )
            
            kb = []
            
            # ✅ 统计每个分类的库存（修复：只统计已同步且激活的代理商品）
            for category in all_categories:
                cat_name = category.get('projectname', '未知分类')
                
                # ✅ 获取该分类下所有激活的代理商品的nowuid列表
                agent_products = list(self.core.config.agent_product_prices.find({
                    'agent_bot_id': self.core.config.AGENT_BOT_ID,
                    'category': cat_name,
                    'is_active': True
                }, {'original_nowuid': 1}))
                
                if not agent_products:
                    continue
                
                # ✅ 提取nowuid列表
                nowuid_list = [ap.get('original_nowuid') for ap in agent_products if ap.get('original_nowuid')]
                
                if not nowuid_list:
                    continue
                
                # ✅ 统计这些商品的实际库存
                stock = self.core.config.hb.count_documents({
                    'nowuid': {'$in': nowuid_list},
                    'state': 0
                })
                
                if stock > 0:  # 只显示有库存的分类
                    button_text = f"{cat_name}  [{stock}个]"
                    kb.append([InlineKeyboardButton(button_text, callback_data=f"category_{cat_name}")])
            
            if not kb:
                self.safe_edit_message(query, "❌ 暂无库存商品", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)
                return
            
            kb.append([InlineKeyboardButton("🏠 主菜单", callback_data="back_main")])
            self.safe_edit_message(query, text, kb, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"❌ 获取商品分类失败: {e}")
            self.safe_edit_message(query, "❌ 加载失败，请重试", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)
            
    def show_category_products(self, query, category: str, page: int = 1):
        """显示分类下的商品（二级分类）"""
        try:
            skip = (page - 1) * 10
            
            # ✅ 从 agent_product_prices 表按 category 字段查询（这样新商品也能显示）
            pipeline = [
                {'$match': {
                    'agent_bot_id': self.core.config.AGENT_BOT_ID,
                    'is_active': True,
                    'category': category  # ✅ 关键：使用 category 字段，不是 leixing
                }},
                {'$lookup': {
                    'from': 'ejfl',
                    'localField': 'original_nowuid',
                    'foreignField': 'nowuid',
                    'as': 'product_info'
                }},
                {'$match': {
                    'product_info': {'$ne': []}
                }},
                {'$skip': skip},
                {'$limit': 10}
            ]
            
            price_docs = list(self.core.config.agent_product_prices.aggregate(pipeline))
            
            # ✅ 提取商品信息并计算库存和价格
            products_with_stock = []
            for pdoc in price_docs:
                if not pdoc.get('product_info'):
                    continue
                
                p = pdoc['product_info'][0]
                nowuid = p.get('nowuid')
                
                # 获取库存
                stock = self.core.get_product_stock(nowuid)
                if stock <= 0:
                    continue
                
                # 获取价格
                price = self.core.get_product_price(nowuid)
                if price is None or price <= 0:
                    continue
                
                p['stock'] = stock
                p['price'] = price
                products_with_stock.append(p)
            
            # 按库存降序排列
            products_with_stock.sort(key=lambda x: -x['stock'])
            
            # ✅ 仿照总部的文本格式
            text = (
                "<b>🛒 这是商品列表  选择你需要的分类：</b>\n\n"
                "❗️没使用过的本店商品的，请先少量购买测试，以免造成不必要的争执！谢谢合作！。\n\n"
                "❗有密码的账户售后时间1小时内，二级未知的账户售后30分钟内！\n\n"
                "❗购买后请第一时间检查账户，提供证明处理售后 超时损失自付！"
            )
            
            kb = []
            for p in products_with_stock:
                name = p.get('projectname')
                nowuid = p.get('nowuid')
                price = p['price']
                stock = p['stock']
                
                # ✅ 按钮格式
                button_text = f"{name} {price}U   [{stock}个]"
                kb.append([InlineKeyboardButton(button_text, callback_data=f"product_{nowuid}")])
            
            # 如果没有有库存的商品
            if not kb:
                kb.append([InlineKeyboardButton("暂无商品耐心等待", callback_data="no_action")])
            
            # ✅ 返回按钮
            kb.append([
                InlineKeyboardButton("🔙 返回", callback_data="back_products"),
                InlineKeyboardButton("❌ 关闭", callback_data=f"close {query.from_user.id}")
            ])
            
            self.safe_edit_message(query, text, kb, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"❌ 获取分类商品失败: {e}")

            self.safe_edit_message(query, "❌ 加载失败，请重试", [[InlineKeyboardButton("🔙 返回", callback_data="back_products")]], parse_mode=None)

    def show_product_detail(self, query, nowuid: str):
        """显示商品详情 - 完全仿照总部格式"""
        try:
            prod = self.core.config.ejfl.find_one({'nowuid': nowuid})
            if not prod:
                self.safe_edit_message(query, "❌ 商品不存在", [[InlineKeyboardButton("🔙 返回", callback_data="back_products")]], parse_mode=None)
                return
            
            price = self.core.get_product_price(nowuid)
            stock = self.core.get_product_stock(nowuid)
            
            if price is None:
                self.safe_edit_message(query, "❌ 商品价格未设置", [[InlineKeyboardButton("🔙 返回", callback_data="back_products")]], parse_mode=None)
                return
            
            # ✅ 完全按照总部的简洁格式
            product_name = self.H(prod.get('projectname', 'N/A'))
            product_status = "✅您正在购买："
            
            text = (
                f"<b>{product_status} {product_name}\n\n</b>"
                f"<b>💰 价格: {price:.2f} USDT\n\n</b>"
                f"<b>📦 库存: {stock}个\n\n</b>"
                f"<b>❗未使用过的本店商品的，请先少量购买测试，以免造成不必要的争执！谢谢合作！\n</b>"
                
            )
            
            kb = []
            if stock > 0:
                kb.append([InlineKeyboardButton("✅ 购买", callback_data=f"buy_{nowuid}"),
                          InlineKeyboardButton("❗使用说明", callback_data="help")])
            else:
                text += "\n\n⚠️ 商品缺货"
                kb.append([InlineKeyboardButton("使用说明", callback_data="help")])
            
            kb.append([InlineKeyboardButton("🏠 主菜单", callback_data="back_main"),
                      InlineKeyboardButton("返回", callback_data=f"category_{prod.get('leixing', '协议号')}")])
            
            self.safe_edit_message(query, text, kb, parse_mode=ParseMode.HTML)
        
        except Exception as e:
            logger.error(f"❌ 获取商品详情失败: {e}")
            self.safe_edit_message(query, "❌ 加载失败，请重试", [[InlineKeyboardButton("🔙 返回", callback_data="back_products")]], parse_mode=None)
            
            
    def handle_buy_product(self, query, nowuid: str):
        """处理购买流程 - 完全仿照总部格式"""
        uid = query.from_user.id
        prod = self.core.config.ejfl.find_one({'nowuid': nowuid})
        price = self.core.get_product_price(nowuid)
        stock = self.core.get_product_stock(nowuid)
        user = self.core.get_user_info(uid)
        bal = user.get('USDT', 0) if user else 0
        max_afford = int(bal // price) if price else 0
        max_qty = min(stock, max_afford)
        
        # ✅ 完全按照总部的格式
        text = (
            f"请输入数量:\n"
            f"格式: 10\n\n"
            f"✅ 您正在购买 - {self.H(prod['projectname'])}\n"
            f"💰 单价: {price} U\n"
            f"🪙 您的余额: {bal:.2f} U\n"
            f"📊 最多可买: {max_qty} 个"
        )
        kb = [
            [InlineKeyboardButton("❌ 取消交易", callback_data=f"product_{nowuid}")]
        ]
        
        # ✅ 保存当前消息的ID（这是要被删除的消息）
        input_msg_id = query.message.message_id
        
        # ✅ 修改消息显示"请输入数量"
        self.safe_edit_message(query, text, kb, parse_mode=None)
        
        # ✅ 保存消息 ID 到状态
        self.user_states[uid] = {
            'state': 'waiting_quantity',
            'product_nowuid': nowuid,
            'input_msg_id': input_msg_id  # ← 保存这条要被删除的消息ID
        }
        
        
    def handle_quantity_input(self, update: Update, context: CallbackContext):
        """处理购买数量输入 - 显示确认页面"""
        uid = update.effective_user.id
        if uid not in self.user_states or self.user_states[uid].get('state') != 'waiting_quantity':
            return
        
        try:
            qty = int(update.message.text.strip())
        except:
            update.message.reply_text("❌ 请输入有效整数")
            return
        
        st = self.user_states[uid]
        nowuid = st['product_nowuid']
        prod = self.core.config.ejfl.find_one({'nowuid': nowuid})
        price = self.core.get_product_price(nowuid)
        stock = self.core.get_product_stock(nowuid)
        user = self.core.get_user_info(uid)
        bal = user.get('USDT', 0) if user else 0
        
        if qty <= 0:
            update.message.reply_text("❌ 数量需 > 0")
            return
        if qty > stock:
            update.message.reply_text(f"❌ 库存不足（当前 {stock}）")
            return
        
        total_cost = price * qty
        if total_cost > bal:
            update.message.reply_text(f"❌ 余额不足，需: {total_cost:.2f}U 当前: {bal:.2f}U")
            return
        
        chat_id = uid
        
        # ✅ 先删除"请输入数量"的消息
        if 'input_msg_id' in st:
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=st['input_msg_id'])
            except Exception as e:
                logger.error(f"删除输入数量消息失败: {e}")
        
        # ✅ 删除用户输入的数字消息
        try:
            update.message.delete()
        except Exception as e:
            logger.error(f"删除用户消息失败: {e}")
        
        # ✅ 显示确认页面（总部格式）
        text = (
            f"<b>✅ 您正在购买 - {self.H(prod['projectname'])}</b>\n\n"
            f"<b>🛍 数量: {qty}</b>\n\n"
            f"<b>💰 价格: {price}</b>\n\n"
            f"<b>🪙 您的余额: {bal:.2f}</b>"
        )
        
        kb = [
            [InlineKeyboardButton("❌ 取消交易", callback_data=f"product_{nowuid}"),
             InlineKeyboardButton("✅ 确认购买", callback_data=f"confirm_buy_{nowuid}_{qty}")],
            [InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]
        ]
        
        # ✅ 用 send_message 发送确认页面
        msg = context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML
        )
        
        # ✅ 保存状态
        self.user_states[uid] = {
            'state': 'confirming_purchase',
            'product_nowuid': nowuid,
            'quantity': qty,
            'confirm_msg_id': msg.message_id  # 只需保存确认页面的ID
        }

    def handle_confirm_buy(self, query, nowuid: str, qty: int, context: CallbackContext):
        """确认购买 - 处理交易"""
        uid = query.from_user.id
        st = self.user_states.pop(uid, None)
        chat_id = query.message.chat_id
        
        # ✅ 删除确认页面的消息
        try:
            query.message.delete()
        except Exception as e:
            logger.error(f"删除确认页面失败: {e}")
        
        # 处理购买
        ok, res = self.core.process_purchase(uid, nowuid, qty)
        
        if ok:
            # ✅ 从环境变量加载通知模板内容
            custom_message_template = os.getenv("PURCHASE_SUCCESS_TEMPLATE", (
                "✅您的账户已打包完成，请查收！\n\n"
                "🔐二级密码:请在json文件中【two2fa】查看！\n\n"
                "⚠️注意：请马上检查账户，1小时内出现问题，联系客服处理！\n"
                "‼️超过售后时间，损失自付，无需多言！\n\n"
                "🔹 9号客服  @o9eth   @o7eth\n"
                "🔹 频道  @idclub9999\n"
                "🔹补货通知  @p5540"
            ))

            # ✅ 发送购买成功通知（不包括订单、商品等细节内容）
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛍️ 继续购买", callback_data="products"),
                 InlineKeyboardButton("👤 个人中心", callback_data="profile")]
            ])
            try:
                context.bot.send_message(
                    chat_id=chat_id,
                    text=os.getenv("PURCHASE_SUCCESS_TEMPLATE"),
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                    )
                logger.info(f"✅ 自定义购买成功通知已发送给用户 {uid}")
            except Exception as msg_error:
                logger.error(f"❌ 发送购买成功通知失败: {msg_error}")
            
            query.answer("✅ 购买成功！")
        else:
            query.answer(f"❌ 购买失败: {res}", show_alert=True)
       
    def show_user_profile(self, query):
        """显示用户个人中心"""
        uid = query.from_user.id
        info = self.core.get_user_info(uid)
        if not info:
            self.safe_edit_message(query, "❌ 用户信息不存在", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)
            return
        
        avg = round(info.get('zgje', 0) / max(info.get('zgsl', 1), 1), 2)
        level = '🥇 金牌' if info.get('zgje', 0) > 100 else '🥈 银牌' if info.get('zgje', 0) > 50 else '🥉 铜牌'
        
        text = (
            f"👤 个人中心\n\n"
            f"ID: {uid}\n"
            f"内部ID: {self.H(info.get('count_id', '-'))}\n"
            f"余额: {info.get('USDT', 0):.2f}U\n"
            f"累计消费: {info.get('zgje', 0):.2f}U  次数:{info.get('zgsl', 0)}\n"
            f"平均订单: {avg:.2f}U\n"
            f"等级: {level}\n"
        )
        
        kb = [
            [InlineKeyboardButton("💰 充值余额", callback_data="recharge"),
             InlineKeyboardButton("📊 订单历史", callback_data="orders")],
            [InlineKeyboardButton("🛍️ 商品中心", callback_data="products"),
             InlineKeyboardButton("📞 联系客服", callback_data="support")],
            [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
        ]
        
        self.safe_edit_message(query, text, kb, parse_mode=None)

    # ========== 充值 UI ==========
    def _format_recharge_text(self, order: Dict) -> str:
        base_amt = Decimal(str(order['base_amount'])).quantize(Decimal("0.01"))
        expected_amt = Decimal(str(order['expected_amount'])).quantize(Decimal("0.0001"))
        expire_bj = self.core._to_beijing(order.get('expire_time')).strftime('%Y-%m-%d %H:%M')
        return (
            "💰 余额充值（自动到账）\n\n"
            f"网络: TRON-TRC20\n"
            f"代币: {self.core.config.TOKEN_SYMBOL}\n"
            f"收款地址: <code>{self.H(order['address'])}</code>\n\n"
            "请按以下“识别金额”精确转账:\n"
            f"应付金额: <b>{expected_amt}</b> USDT\n"
            f"基础金额: {base_amt} USDT\n"
            f"识别码: {order['unique_code']}\n\n"
            f"有效期至: {expire_bj} （10分钟内未支付该订单失效）\n\n"
            "注意:\n"
            "• 必须精确到 4 位小数的“应付金额”\n"
            "• 系统自动监听入账，无需手动校验"
        )

    def show_recharge_options(self, query):
        uid = query.from_user.id
        text = ("💰 余额充值\n\n"
                "• 固定地址收款，自动到账\n"
                f"• 最低金额: {self.core.config.RECHARGE_MIN_USDT} USDT\n"
                f"• 有效期: 10分钟\n"
                f"• 轮询间隔: {self.core.config.RECHARGE_POLL_INTERVAL_SECONDS}s\n\n"
                "请选择金额或发送自定义金额（数字）：")
        kb = [
            [InlineKeyboardButton("10 USDT", callback_data="recharge_amount_10"),
             InlineKeyboardButton("30 USDT", callback_data="recharge_amount_30"),
             InlineKeyboardButton("50 USDT", callback_data="recharge_amount_50")],
            [InlineKeyboardButton("100 USDT", callback_data="recharge_amount_100"),
             InlineKeyboardButton("200 USDT", callback_data="recharge_amount_200"),
             InlineKeyboardButton("500 USDT", callback_data="recharge_amount_500")],
            [InlineKeyboardButton("📜 充值记录", callback_data="recharge_list"),
             InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
        ]
        self.user_states[uid] = {'state': 'waiting_recharge_amount'}
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def _show_created_recharge_order(self, chat_or_query, order: Dict, edit_query=None):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 充值记录", callback_data="recharge_list"),
             InlineKeyboardButton("❌ 取消订单", callback_data=f"recharge_cancel_{str(order['_id'])}")],
            [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
        ])
        try:
            chat_id = (edit_query.message.chat_id if edit_query
                       else (chat_or_query.chat_id if hasattr(chat_or_query, 'chat_id')
                             else chat_or_query.message.chat_id))
            self.core.send_plain_qr_with_caption(chat_id, order, kb)
        except Exception as e:
            logger.warning(f"发送二维码caption失败: {e}")
            fallback = self._format_recharge_text(order)
            if edit_query:
                self.safe_edit_message(edit_query, fallback, kb.inline_keyboard, parse_mode=ParseMode.HTML)
            else:
                chat_or_query.reply_text(fallback, reply_markup=kb, parse_mode=ParseMode.HTML)

    def handle_recharge_amount_input(self, update: Update, amount: Decimal):
        uid = update.effective_user.id
        ok, msg, order = self.core.create_recharge_order(uid, amount)
        if not ok:
            update.message.reply_text(f"❌ {msg}")
            return
        self.user_states.pop(uid, None)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 充值记录", callback_data="recharge_list"),
             InlineKeyboardButton("❌ 取消订单", callback_data=f"recharge_cancel_{str(order['_id'])}")],
            [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
        ])
        try:
            self.core.send_plain_qr_with_caption(update.message.chat_id, order, kb)
        except Exception as e:
            logger.warning(f"发送二维码caption失败(text输入): {e}")
            update.message.reply_text(self._format_recharge_text(order), reply_markup=kb, parse_mode=ParseMode.HTML)

    def show_recharge_list(self, query):
        uid = query.from_user.id
        recs = self.core.list_recharges(uid, limit=10, include_canceled=False)
        if not recs:
            self.safe_edit_message(query, "📜 最近充值记录\n\n暂无记录", [[InlineKeyboardButton("🔙 返回", callback_data="recharge")]], parse_mode=None)
            return
        text = "📜 最近充值记录（最新优先）\n\n"
        for r in recs:
            st = r.get('status')
            ba = Decimal(str(r.get('base_amount', 0))).quantize(Decimal("0.01"))
            ea = Decimal(str(r.get('expected_amount', 0))).quantize(Decimal("0.0001"))
            ct = r.get('created_time'); ct_s = self.core._to_beijing(ct).strftime('%m-%d %H:%M') if ct else '-'
            ex = r.get('expire_time'); ex_s = self.core._to_beijing(ex).strftime('%m-%d %H:%M') if ex else '-'
            tx = r.get('tx_id') or '-'
            text += f"• {st} | 基:{ba}U | 应:{ea}U | 创建:{ct_s} | 过期:{ex_s} | Tx:{self.H(tx[:14] + '...' if len(tx)>14 else tx)}\n"
        kb = [
            [InlineKeyboardButton("🔙 返回充值", callback_data="recharge"),
             InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]
        ]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    # ========== 价格管理 / 报表 ==========
    def show_price_management(self, query, page: int = 1):
        uid = query.from_user.id
        if uid not in ADMIN_USERS:
            self.safe_edit_message(query, "❌ 无权限", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)
            return
        res = self.core.get_agent_product_list(uid, page)
        prods = res['products']
        if not prods:
            self.safe_edit_message(query, "❌ 暂无商品可管理", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)
            return
        text = f"💰 价格管理（第{page}页）\n\n"
        kb = []
        for p in prods:
            info = p['product_info'][0] if p['product_info'] else {}
            name = info.get('projectname', 'N/A')
            nowuid = p.get('original_nowuid', '')
            
            # ✅ 实时获取总部价格
            origin_price = float(info.get('money', 0))
            
            # ✅ 获取代理的加价标记
            agent_markup = float(p.get('agent_markup', 0))
            
            # ✅ 实时计算代理价格
            agent_price = round(origin_price + agent_markup, 2)
            
            # ✅ 计算当前利润率
            profit_rate = (agent_markup / origin_price * 100) if origin_price else 0
            
            stock = self.core.get_product_stock(nowuid)
            text += f"{self.H(name)}\n总部:{origin_price}U  加价:{agent_markup:.2f}U  代理价:{agent_price}U  利润率:{profit_rate:.1f}%  库:{stock}\n\n"
            kb.append([InlineKeyboardButton(f"📝 {name[:18]}", callback_data=f"edit_price_{nowuid}")])
        pag = []
        if page > 1:
            pag.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"price_page_{page-1}"))
        if res['current_page'] < res['total_pages']:
            pag.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"price_page_{page+1}"))
        if pag:
            kb.append(pag)
        kb.append([InlineKeyboardButton("🏠 主菜单", callback_data="back_main")])
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_price_edit(self, query, nowuid: str):
        prod = self.core.config.ejfl.find_one({'nowuid': nowuid})
        if not prod:
            self.safe_edit_message(query, "❌ 商品不存在", [[InlineKeyboardButton("🔙 返回", callback_data="price_management")]], parse_mode=None)
            return
        ap_info = self.core.config.agent_product_prices.find_one({
            'agent_bot_id': self.core.config.AGENT_BOT_ID, 'original_nowuid': nowuid
        })
        if not ap_info:
            self.safe_edit_message(query, "❌ 代理价格配置不存在", [[InlineKeyboardButton("🔙 返回", callback_data="price_management")]], parse_mode=None)
            return
        
        # ✅ 实时获取总部价格
        op = float(prod.get('money', 0))
        
        # ✅ 获取代理加价标记
        agent_markup = float(ap_info.get('agent_markup', 0))
        
        # ✅ 实时计算代理价格
        agent_price = round(op + agent_markup, 2)
        
        # ✅ 计算利润率
        profit_rate = (agent_markup / op * 100) if op > 0 else 0
        
        stock = self.core.get_product_stock(nowuid)
        text = f"""📝 编辑商品价格

🏷️ 商品: {self.H(prod['projectname'])}
📦 库存: {stock}
💼 编号: {self.H(nowuid)}

💰 当前价格:
• 总部: {op}U
• 加价: {agent_markup:.2f}U
• 代理价: {agent_price:.2f}U
• 利润率: {profit_rate:.1f}%

请直接发送新的代理价格数字，例如: {op + 0.2:.2f}
"""
        self.user_states[query.from_user.id] = {'state': 'waiting_price', 'product_nowuid': nowuid, 'original_price': op}
        kb = [
            [InlineKeyboardButton("🔄 切换状态", callback_data=f"toggle_status_{nowuid}"),
             InlineKeyboardButton("📊 利润预算", callback_data=f"profit_calc_{nowuid}")],
            [InlineKeyboardButton("🔙 返回管理", callback_data="price_management")]
        ]
        self.safe_edit_message(query, text, kb, parse_mode=ParseMode.HTML)

    def show_profit_calculator(self, query, nowuid: str):
        ap_info = self.core.config.agent_product_prices.find_one({
            'agent_bot_id': self.core.config.AGENT_BOT_ID, 'original_nowuid': nowuid
        })
        if not ap_info:
            self.safe_edit_message(query, "❌ 商品不存在", [[InlineKeyboardButton("🔙 返回", callback_data="price_management")]], parse_mode=None)
            return
        
        # ✅ 实时获取总部价格
        prod = self.core.config.ejfl.find_one({'nowuid': nowuid})
        op = float(prod.get('money', 0)) if prod else 0
        
        name = ap_info.get('product_name', 'N/A')
        text = f"📊 利润计算器 - {self.H(name)}\n总部: {op}U（实时价格）\n\n"
        kb = []
        
        for rate in [10, 20, 30, 50, 80, 100]:
            # ✅ 计算新的加价标记
            new_markup = round(op * rate / 100, 2)
            # ✅ 实时计算代理价格
            new_agent_price = round(op + new_markup, 2)
            text += f"{rate}% → {new_agent_price:.2f}U (加价:{new_markup:.2f})\n"
            kb.append([InlineKeyboardButton(f"设置 {rate}%({new_agent_price})", callback_data=f"set_price_{nowuid}_{new_agent_price}")])
        
        kb.append([InlineKeyboardButton("🔙 返回编辑", callback_data=f"edit_price_{nowuid}")])
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_system_reports(self, query):
        uid = query.from_user.id
        if uid not in ADMIN_USERS:
            self.safe_edit_message(query, "❌ 无权限", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)
            return
        text = ("📊 系统报表中心\n\n"
                "请选择需要查看的报表类型：")
        kb = [
            [InlineKeyboardButton("📈 销售报表(30天)", callback_data="report_sales_30"),
             InlineKeyboardButton("👥 用户报表", callback_data="report_users")],
            [InlineKeyboardButton("📦 商品报表", callback_data="report_products"),
             InlineKeyboardButton("💰 财务报表(30天)", callback_data="report_financial_30")],
            [InlineKeyboardButton("📊 综合概览", callback_data="report_overview_quick"),
             InlineKeyboardButton("🔄 刷新数据", callback_data="system_reports")],
            [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
        ]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_sales_report(self, query, days: int = 30):
        s = self.core.get_sales_statistics(days)
        text = (f"📈 销售报表（{days}天）\n"
                f"总订单:{s['total_orders']}  总销售额:{s['total_revenue']:.2f}U  总销量:{s['total_quantity']}\n"
                f"平均订单额:{s['avg_order_value']:.2f}U\n\n"
                f"今日 订单:{s['today_orders']}  销售:{s['today_revenue']:.2f}U  量:{s['today_quantity']}\n\n"
                "🏆 热销TOP5：\n")
        if s['popular_products']:
            for i,p in enumerate(s['popular_products'],1):
                text += f"{i}. {self.H(p['_id'])}  数量:{p['total_sold']}  销售:{p['total_revenue']:.2f}U\n"
        else:
            text += "暂无数据\n"
        kb = [
            [InlineKeyboardButton("📅 7天", callback_data="report_sales_7"),
             InlineKeyboardButton("📅 30天", callback_data="report_sales_30"),
             InlineKeyboardButton("📅 90天", callback_data="report_sales_90")],
            [InlineKeyboardButton("🔄 刷新", callback_data=f"report_sales_{days}"),
             InlineKeyboardButton("🔙 返回报表", callback_data="system_reports")]
        ]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_user_report(self, query):
        st = self.core.get_user_statistics()
        text = (f"👥 用户统计报表\n"
                f"总:{st['total_users']}  活跃:{st['active_users']}  今日新增:{st['today_new_users']}  活跃率:{st['activity_rate']}%\n"
                f"余额总:{st['total_balance']:.2f}U  平均:{st['avg_balance']:.2f}U  消费总:{st['total_spent']:.2f}U\n"
                f"等级分布  铜:{st['spending_levels']['bronze']}  银:{st['spending_levels']['silver']}  金:{st['spending_levels']['gold']}")
        kb=[[InlineKeyboardButton("🔄 刷新", callback_data="report_users"),
             InlineKeyboardButton("🔙 返回报表", callback_data="system_reports")]]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_overview_report(self, query):
        s = self.core.get_sales_statistics(30)
        u = self.core.get_user_statistics()
        text = (f"📊 系统概览报表(30天)\n\n"
                f"用户:{u['total_users']}  活跃:{u['active_users']}  今日新增:{u['today_new_users']}\n"
                f"订单:{s['total_orders']}  销售:{s['total_revenue']:.2f}U  今日:{s['today_revenue']:.2f}U\n"
                f"平均订单额:{s['avg_order_value']:.2f}U  活跃率:{u['activity_rate']}%")
        kb=[[InlineKeyboardButton("🔄 刷新", callback_data="report_overview_quick"),
             InlineKeyboardButton("🔙 返回报表", callback_data="system_reports")]]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_product_report(self, query):
        p = self.core.get_product_statistics()
        text = (f"📦 商品统计报表\n"
                f"商品:{p['total_products']}  启用:{p['active_products']}  禁用:{p['inactive_products']}\n"
                f"库存:{p['total_stock']}  已售:{p['sold_stock']}  周转率:{p['stock_turnover_rate']}%\n"
                f"平均利润率:{p['avg_profit_rate']}%  最高:{p['highest_profit_rate']}%  最低:{p['lowest_profit_rate']}%")
        kb=[[InlineKeyboardButton("🔄 刷新", callback_data="report_products"),
             InlineKeyboardButton("🔙 返回报表", callback_data="system_reports")]]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_financial_report(self, query, days: int = 30):
        f = self.core.get_financial_statistics(days)
        text = (f"💰 财务报表（{days}天）\n"
                f"总收入:{f['total_revenue']:.2f}U  订单数:{f['order_count']}  平均订单:{f['avg_order_value']:.2f}U\n"
                f"预估利润:{f['estimated_profit']:.2f}U  利润率:{f['profit_margin']}%")
        kb = [
            [InlineKeyboardButton("📅 7天", callback_data="report_financial_7"),
             InlineKeyboardButton("📅 30天", callback_data="report_financial_30"),
             InlineKeyboardButton("📅 90天", callback_data="report_financial_90")],
            [InlineKeyboardButton("🔄 刷新", callback_data=f"report_financial_{days}"),
             InlineKeyboardButton("🔙 返回报表", callback_data="system_reports")]
        ]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    # ========== 其它 ==========
    def show_support_info(self, query):
        text = "📞 客服 @9haokf\n请描述问题 + 用户ID/订单号，便于快速处理。"
        kb = [
            [InlineKeyboardButton("💬 联系客服", url="https://t.me/9haokf")],
            [InlineKeyboardButton("👤 个人中心", callback_data="profile"),
             InlineKeyboardButton("❓ 使用帮助", callback_data="help")],
            [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
        ]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_help_info(self, query):
        text = (
            "❓ 使用帮助\n\n"
            "• 购买：分类 -> 商品 -> 立即购买 -> 输入数量\n"
            "• 充值：进入充值 -> 选择金额或输入金额 -> 按识别金额精确转账\n"
            "• 自动监听入账，无需手动校验\n"
            "• 有问题联系人工客服 @9haokf"
        )
        kb = [
            [InlineKeyboardButton("📞 联系客服", callback_data="support"),
             InlineKeyboardButton("🛍️ 商品中心", callback_data="products")],
            [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
        ]
        self.safe_edit_message(query, text, kb, parse_mode=None)

    def show_order_history(self, query):
        self.safe_edit_message(query, "📊 订单历史功能暂未实现", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)

    # ========== 回调分发 ==========
    def button_callback(self, update: Update, context: CallbackContext):
        q = update.callback_query
        d = q.data
        try:
            logger.info(f"[DEBUG] callback data: {d}")

            # 基础导航
            if d == "products":
                self.show_product_categories(q); q.answer(); return
            elif d == "profile":
                self.show_user_profile(q); q.answer(); return
            elif d == "recharge":
                self.show_recharge_options(q); q.answer(); return
            elif d == "orders":
                self.show_order_history(q); q.answer(); return
            elif d == "support":
                self.show_support_info(q); q.answer(); return
            elif d == "help":
                self.show_help_info(q); q.answer(); return
            elif d == "back_main":
                self.show_main_menu(q); q.answer(); return
            elif d == "back_products":
                self.show_product_categories(q); q.answer(); return

            # 价格管理 / 报表
            elif d == "price_management":
                self.show_price_management(q); q.answer(); return
            elif d.startswith("price_page_"):
                self.show_price_management(q, int(d.replace("price_page_",""))); q.answer(); return
            elif d.startswith("edit_price_"):
                self.show_price_edit(q, d.replace("edit_price_","")); q.answer(); return
            elif d == "system_reports":
                self.show_system_reports(q); q.answer(); return
            elif d == "report_sales_7":
                self.show_sales_report(q,7); q.answer(); return
            elif d == "report_sales_30":
                self.show_sales_report(q,30); q.answer(); return
            elif d == "report_sales_90":
                self.show_sales_report(q,90); q.answer(); return
            elif d == "report_users":
                self.show_user_report(q); q.answer(); return
            elif d == "report_overview_quick":
                self.show_overview_report(q); q.answer(); return
            elif d == "report_products":
                self.show_product_report(q); q.answer(); return
            elif d == "report_financial_7":
                self.show_financial_report(q,7); q.answer(); return
            elif d == "report_financial_30":
                self.show_financial_report(q,30); q.answer(); return
            elif d == "report_financial_90":
                self.show_financial_report(q,90); q.answer(); return

            elif d.startswith("toggle_status_"):
                nowuid = d.replace("toggle_status_","")
                ok, msg = self.core.toggle_product_status(nowuid)
                q.answer(msg)
                if ok:
                    self.show_price_edit(q, nowuid)
                return
            elif d.startswith("profit_calc_"):
                self.show_profit_calculator(q, d.replace("profit_calc_","")); q.answer(); return
            elif d.startswith("set_price_"):
                parts = d.replace("set_price_","").split("_")
                nowuid, np = parts[0], float(parts[1])
                ok, msg = self.core.update_agent_price(nowuid, np)
                q.answer(msg)
                if ok:
                    self.show_price_edit(q, nowuid)
                return

            # 商品相关
            elif d.startswith("category_page_"):
                _, cat, p = d.split("_", 2)
                self.show_category_products(q, cat, int(p)); q.answer(); return
            elif d.startswith("category_"):
                self.show_category_products(q, d.replace("category_","")); q.answer(); return
            elif d.startswith("product_"):
                self.show_product_detail(q, d.replace("product_","")); q.answer(); return
            elif d.startswith("buy_"):
                self.handle_buy_product(q, d.replace("buy_","")); q.answer(); return
            elif d.startswith("confirm_buy_"):
                # ✅ 处理确认购买
                try:
                    parts = d.replace("confirm_buy_", "").split("_")
                    nowuid = parts[0]
                    qty = int(parts[1])
                    self.handle_confirm_buy(q, nowuid, qty, context)  # ← 加上 context
                    q.answer()
                except Exception as e:
                    logger.error(f"确认购买异常: {e}")
                    q.answer("参数错误", show_alert=True)
                return
                
                self.handle_confirm_buy(q, nowuid, qty)
                q.answer()
                return
            # 利润中心
            elif d == "profit_center":
                self.show_profit_center(q); q.answer(); return
            elif d == "profit_withdraw":
                self.start_withdrawal(q); q.answer(); return
            elif d == "profit_withdraw_list":
                self.show_withdrawal_list(q); q.answer(); return

            # 充值金额快捷按钮
            elif d.startswith("recharge_amount_"):
                uid = q.from_user.id
                try:
                    amt = Decimal(d.replace("recharge_amount_", "")).quantize(Decimal("0.01"))
                except Exception:
                    q.answer("金额格式错误", show_alert=True); return
                ok, msg, order = self.core.create_recharge_order(uid, amt)
                if not ok:
                    q.answer(msg, show_alert=True); return
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📜 充值记录", callback_data="recharge_list"),
                     InlineKeyboardButton("❌ 取消订单", callback_data=f"recharge_cancel_{str(order['_id'])}")],
                    [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
                ])
                try:
                    self.core.send_plain_qr_with_caption(q.message.chat_id, order, kb)
                except Exception as e:
                    logger.warning(f"发送二维码caption失败(callback): {e}")
                    self.safe_edit_message(q, self._format_recharge_text(order), kb, parse_mode=ParseMode.HTML)
                q.answer("已生成识别金额，请按应付金额转账"); return

            elif d == "recharge_list":
                self.show_recharge_list(q); q.answer(); return

            # 订单取消
            elif d.startswith("recharge_cancel_"):
                oid = d.replace("recharge_cancel_", "")
                delete_mode = self.core.config.RECHARGE_DELETE_ON_CANCEL
                try:
                    order = self.core.config.recharge_orders.find_one({'_id': ObjectId(oid)})
                    res = self.core.config.recharge_orders.update_one(
                        {'_id': ObjectId(oid), 'status': 'pending'},
                        {'$set': {'status': 'canceled', 'canceled_time': datetime.utcnow()}}
                    )
                    if res.modified_count:
                        q.answer("已取消")
                        kb = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📜 充值记录", callback_data="recharge_list"),
                             InlineKeyboardButton("🏠 返回主菜单", callback_data="back_main")]
                        ])
                        if delete_mode:
                            # 删除原消息后发新提示
                            try:
                                chat_id = q.message.chat_id
                                q.message.delete()
                                Bot(self.core.config.BOT_TOKEN).send_message(
                                    chat_id=chat_id,
                                    text="❌ 该充值订单已取消。\n请重新选择金额创建新的订单。",
                                    reply_markup=kb
                                )
                            except Exception as e_del:
                                logger.warning(f"删除订单消息失败: {e_del}")
                                # 回退编辑 caption
                                try:
                                    q.edit_message_caption(
                                        caption="❌ 该充值订单已取消。\n请重新选择金额创建新的订单。",
                                        reply_markup=kb,
                                        parse_mode=ParseMode.HTML
                                    )
                                except Exception as e_cap:
                                    logger.warning(f"编辑取消 caption 失败: {e_cap}")
                        else:
                            # 仅编辑原消息 caption
                            try:
                                q.edit_message_caption(
                                    caption="❌ 该充值订单已取消。\n请重新选择金额创建新的订单。",
                                    reply_markup=kb,
                                    parse_mode=ParseMode.HTML
                                )
                            except Exception as e_cap:
                                logger.warning(f"编辑取消 caption 失败: {e_cap}")
                                Bot(self.core.config.BOT_TOKEN).send_message(
                                    chat_id=q.message.chat_id,
                                    text="❌ 该充值订单已取消。\n请重新选择金额创建新的订单。",
                                    reply_markup=kb
                                )
                    else:
                        q.answer("无法取消（已过期/已支付/不存在）", show_alert=True)
                except Exception as e:
                    logger.warning(f"取消订单异常: {e}")
                    q.answer("取消失败", show_alert=True)
                return

            # 通用操作
            elif d == "no_action":
                q.answer(); return
            elif d.startswith("close "):
                try:
                    q.message.delete()
                except:
                    pass
                q.answer(); return

            else:
                self.safe_edit_message(q, "❓ 未知操作", [[InlineKeyboardButton("🏠 主菜单", callback_data="back_main")]], parse_mode=None)
                q.answer(); return

        except Exception as e:
            if "Message is not modified" in str(e):
                try:
                    q.answer("界面已是最新")
                except:
                    pass
            else:
                logger.warning(f"按钮处理异常: {e}")
                traceback.print_exc()
                try:
                    q.answer("操作异常", show_alert=True)
                except:
                    pass
                try:
                    q.edit_message_text("❌ 操作失败，请重试")
                except:
                    pass

    # ========== 文本消息状态处理 ==========
    def handle_text_message(self, update: Update, context: CallbackContext):
        """处理文本消息"""
        uid = update.effective_user.id
        if uid not in self.user_states:
            return
        
        st = self.user_states[uid]
        try:
            if st.get('state') == 'waiting_quantity':
                # ✅ 处理购买数量输入
                self.handle_quantity_input(update, context)
                return
            
            elif st.get('state') == 'waiting_price':
                try:
                    new_price = float(update.message.text.strip())
                except:
                    update.message.reply_text("❌ 请输入有效的价格数字")
                    return
                nowuid = st['product_nowuid']
                op = st['original_price']
                if new_price < op:
                    update.message.reply_text(f"❌ 代理价格不能低于总部价格 {op} USDT")
                    return
                self.user_states.pop(uid, None)
                ok, msg = self.core.update_agent_price(nowuid, new_price)
                update.message.reply_text(("✅ " if ok else "❌ ") + msg)
                return
            
            elif st.get('state') == 'waiting_withdraw_amount':
                self.handle_withdraw_amount_input(update)
                return
            
            elif st.get('state') == 'waiting_withdraw_address':
                self.handle_withdraw_address_input(update)
                return
            
            elif st.get('state') == 'waiting_recharge_amount':
                txt = update.message.text.strip()
                try:
                    amt = Decimal(txt).quantize(Decimal("0.01"))
                except Exception:
                    update.message.reply_text("❌ 金额格式错误，请输入数字（例如 12 或 12.5）")
                    return
                self.handle_recharge_amount_input(update, amt)
                return
        
        except Exception as e:
            logger.error(f"文本处理异常: {e}")
            update.message.reply_text("❌ 处理异常，请重试")
            if uid in self.user_states:
                self.user_states.pop(uid, None)


class AgentBot:
    """主入口（自动轮询充值）"""

    def __init__(self, token: str):
        self.config = AgentBotConfig()
        self.core = AgentBotCore(self.config)
        self.handlers = AgentBotHandlers(self.core)
        self.updater = Updater(token=token, use_context=True)
        self.dispatcher = self.updater.dispatcher

    def setup_handlers(self):
        self.dispatcher.add_handler(CommandHandler("start", self.handlers.start_command))
        self.dispatcher.add_handler(CallbackQueryHandler(self.handlers.button_callback))
        self.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handlers.handle_text_message))
        logger.info("✅ 处理器设置完成")

        try:
            self.updater.job_queue.run_repeating(
                self._job_auto_recharge_check,
                interval=self.config.RECHARGE_POLL_INTERVAL_SECONDS,
                first=5
            )
            logger.info(f"✅ 已启动充值自动校验任务（间隔 {self.config.RECHARGE_POLL_INTERVAL_SECONDS}s）")
        except Exception as e:
            logger.warning(f"启动自动校验任务失败: {e}")

    def _job_auto_recharge_check(self, context: CallbackContext):
        try:
            self.core.poll_and_auto_settle_recharges(max_orders=80)
        except Exception as e:
            logger.warning(f"自动校验任务异常: {e}")

    def run(self):
        try:
            self.setup_handlers()
            self.updater.start_polling()
            logger.info("🚀 机器人启动成功，开始监听消息...")
            self.updater.idle()
        except Exception as e:
            logger.error(f"❌ 机器人运行失败: {e}")
            raise


def main():
    if len(sys.argv) >= 2 and not sys.argv[1].startswith("--env"):
        token = sys.argv[1]
    else:
        token = os.getenv("BOT_TOKEN")
    if not token:
        print("用法: python agent_bot.py <BOT_TOKEN> [--env yourenvfile]")
        sys.exit(1)
    print("🤖 华南代理机器人（统一通知 + + 10分钟有效 + 取消修复版）")
    print(f"📡 Token: {token[:10]}...")
    print(f"⏰ 启动(北京时间): {(datetime.utcnow()+timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    try:
        bot = AgentBot(token)
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 机器人停止运行")
    except Exception as e:
        print(f"\n❌ 机器人运行错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
