import json
import random
import re
import pymongo
from pymongo.collection import Collection
import logging
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv
import os
import threading

# 加载环境变量
load_dotenv()

# ✅ 初始化日志系统
def init_logging():
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(f"{log_dir}/init.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    logging.info("📌 日志系统初始化完成")

init_logging()

# ✅ 环境变量配置集中管理
class Config:
    # MongoDB 配置
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017/')
    MONGO_DB_BOT = os.getenv('MONGO_DB_BOT', '9hao1bot')
    MONGO_DB_XCHP = os.getenv('MONGO_DB_XCHP', '9hao1bot')
    MONGO_DB_MAIN = os.getenv('MONGO_DB_MAIN', 'qukuailian')
    
    # 客服联系方式
    CUSTOMER_SERVICE = os.getenv('CUSTOMER_SERVICE', '@o9eth')
    OFFICIAL_CHANNEL = os.getenv('OFFICIAL_CHANNEL', '@o9eth')
    RESTOCK_GROUP = os.getenv('RESTOCK_GROUP', 'https://t.me/+EeTF1qOe_MoyMzQ0')
    
    # Bot 配置
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BOT_USERNAME = os.getenv('BOT_USERNAME', '9hao1bot')
    NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", "0"))
    
    # 时间配置
    STOCK_NOTIFICATION_DELAY = int(os.getenv('STOCK_NOTIFICATION_DELAY', '3'))
    MESSAGE_DELETE_DELAY = int(os.getenv('MESSAGE_DELETE_DELAY', '3'))
    
    # 验证关键配置
    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("❌ BOT_TOKEN 环境变量未设置")
        if cls.NOTIFY_CHANNEL_ID == 0:
            logging.warning("⚠️ NOTIFY_CHANNEL_ID 未设置，库存通知可能无法正常工作")

# 验证配置
Config.validate()

# ✅ 使用配置类的值
MONGO_URI = Config.MONGO_URI
MONGO_DB_BOT = Config.MONGO_DB_BOT
MONGO_DB_XCHP = Config.MONGO_DB_XCHP
MONGO_DB_MAIN = Config.MONGO_DB_MAIN
CUSTOMER_SERVICE = Config.CUSTOMER_SERVICE
OFFICIAL_CHANNEL = Config.OFFICIAL_CHANNEL
RESTOCK_GROUP = Config.RESTOCK_GROUP
BOT_TOKEN = Config.BOT_TOKEN
NOTIFY_CHANNEL_ID = Config.NOTIFY_CHANNEL_ID
STOCK_NOTIFICATION_DELAY = Config.STOCK_NOTIFICATION_DELAY
BOT_USERNAME = Config.BOT_USERNAME

# ✅ 数据库连接和集合管理优化
class DatabaseManager:
    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        
        # 主数据库
        self.main_db = self.client[MONGO_DB_MAIN]
        self.qukuai = self.main_db['qukuai']
        
        # 机器人数据库
        self.bot_db = self.client[MONGO_DB_BOT]
        self._init_collections()
        
        logging.info("✅ 数据库连接初始化完成")
    
    def _init_collections(self):
        """初始化所有集合"""
        self.user = self.bot_db['user']
        self.shangtext = self.bot_db['shangtext']
        self.get_key = self.bot_db['get_key']
        self.topup = self.bot_db['topup']
        self.get_kehuduan = self.bot_db['get_kehuduan']
        self.shiyong = self.bot_db['shiyong']
        self.user_log = self.bot_db['user_log']
        self.fenlei = self.bot_db['fenlei']
        self.ejfl = self.bot_db['ejfl']
        self.hb = self.bot_db['hb']
        self.xyh = self.bot_db['xyh']
        self.gmjlu = self.bot_db['gmjlu']
        self.fyb = self.bot_db['fyb']
        self.sftw = self.bot_db['sftw']
        self.hongbao = self.bot_db['hongbao']
        self.qb = self.bot_db['qb']
        self.zhuanz = self.bot_db['zhuanz']
        self.withdrawal_requests = self.bot_db['withdrawal_requests']
    
    def close(self):
        """关闭数据库连接"""
        self.client.close()
        logging.info("✅ 数据库连接已关闭")

# 初始化数据库管理器
db_manager = DatabaseManager()

# ✅ 为了向后兼容，保留原有变量名
teleclient = db_manager.client
main_db = db_manager.main_db
qukuai = db_manager.qukuai
bot_db = db_manager.bot_db
user = db_manager.user
shangtext = db_manager.shangtext
get_key = db_manager.get_key
topup = db_manager.topup
get_kehuduan = db_manager.get_kehuduan
shiyong = db_manager.shiyong
user_log = db_manager.user_log
fenlei = db_manager.fenlei
ejfl = db_manager.ejfl
hb = db_manager.hb
xyh = db_manager.xyh
gmjlu = db_manager.gmjlu
fyb = db_manager.fyb
sftw = db_manager.sftw
hongbao = db_manager.hongbao
qb = db_manager.qb
zhuanz = db_manager.zhuanz
withdrawal_requests = db_manager.withdrawal_requests

# ✅ 库存通知管理优化
class StockNotificationManager:
    def __init__(self):
        self.notify_cache = {}
        self.last_notify_time = {}
        self.notification_lock = threading.Lock()
        self.bot_instance = None
    
    def get_bot(self):
        """获取或创建 Bot 实例"""
        if self.bot_instance is None:
            self.bot_instance = Bot(token=BOT_TOKEN)
        return self.bot_instance
    
    def add_stock_notification(self, nowuid: str, projectname: str):
        """添加库存通知"""
        with self.notification_lock:
            if nowuid not in self.notify_cache:
                self.notify_cache[nowuid] = {'projectname': projectname, 'count': 1}
            else:
                self.notify_cache[nowuid]['count'] += 1
    
    def send_notification(self, nowuid: str, projectname: str, price: float, stock: int, count: int):
        """发送单个商品的库存通知"""
        try:
            if count <= 0:
                logging.info(f"ℹ️ 补货数为0，跳过通知：nowuid={nowuid}")
                return
            
            # 分离一级分类和二级分类名称
            if "/" in projectname:
                parent_name, product_name = projectname.split("/", 1)
            else:
                parent_name = "未分类"
                product_name = projectname
            
            text = f"""
<b>💭💭 库存更新💭💭</b>

<b>{parent_name} /{product_name}</b>

<b>💰 商品价格：{price:.2f} U</b>

<b>🆕 新增库存：{count} 个</b>

<b>📊 剩余库存：{stock} 个</b>

<b>🛒 点击下方按钮快速购买</b>
            """.strip()

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 购买商品", url=f"https://t.me/{BOT_USERNAME}?start=buy_{nowuid}")]
            ])
            
            bot = self.get_bot()
            bot.send_message(
                chat_id=NOTIFY_CHANNEL_ID, 
                text=text, 
                parse_mode='HTML', 
                reply_markup=keyboard
            )
            logging.info(f"✅ 补货通知已发送：{projectname} (新增{count}个)")
        except Exception as e:
            logging.error(f"❌ 推送失败：{e}")
    
    def send_batched_notifications(self):
        """发送批量库存通知"""
        with self.notification_lock:
            if not self.notify_cache:
                return
            
            notifications_to_send = self.notify_cache.copy()
            self.notify_cache.clear()
        
        for nowuid, info in notifications_to_send.items():
            try:
                # 获取二级分类信息
                product = ejfl.find_one({'nowuid': nowuid})
                if not product:
                    logging.warning(f"❌ 未找到商品信息：nowuid={nowuid}")
                    continue
                
                # 获取一级分类信息
                uid = product.get('uid')
                parent_category = fenlei.find_one({'uid': uid})
                parent_name = parent_category['projectname'] if parent_category else "未知分类"
                
                # 构建完整的商品名称：一级分类/二级分类
                product_name = f"{parent_name}/{product['projectname']}"
                
                price = float(product.get('money', 0))
                stock = hb.count_documents({'nowuid': nowuid, 'state': 0})
                self.send_notification(nowuid, product_name, price, stock, info['count'])
                
            except Exception as e:
                logging.error(f"❌ 发送库存通知失败：nowuid={nowuid}, error={e}")
        
        logging.info(f"📢 批量库存通知完成，共发送 {len(notifications_to_send)} 个通知")
    
    def schedule_notification(self, nowuid: str, projectname: str):
        """安排延迟通知"""
        self.add_stock_notification(nowuid, projectname)
        
        def delayed_notify():
            time.sleep(STOCK_NOTIFICATION_DELAY)
            try:
                self.send_batched_notifications()
            except Exception as e:
                logging.error(f"❌ 延迟通知失败：{e}")
        
        threading.Thread(target=delayed_notify, daemon=True).start()
        logging.info(f"🔔 已启动库存通知延迟任务：{projectname} (nowuid={nowuid})")

# 初始化库存通知管理器
stock_manager = StockNotificationManager()

# ✅ 为了向后兼容，保留原有变量和函数
stock_notify_cache = stock_manager.notify_cache
last_notify_time = stock_manager.last_notify_time
notification_lock = stock_manager.notification_lock

def send_stock_notification(bot: Bot, channel_id: int, projectname: str, price: float, stock: int, nowuid: str, bot_username: str = None):
    """向后兼容的库存通知函数"""
    if bot_username is None:
        bot_username = BOT_USERNAME
    
    count = stock_notify_cache.get(nowuid, {}).get('count', 0)
    stock_manager.send_notification(nowuid, projectname, price, stock, count)

def send_batched_stock_notifications(bot: Bot, channel_id: int):
    """向后兼容的批量通知函数"""
    stock_manager.send_batched_notifications()

def shang_text(projectname, text):
    """统一的商店文本插入函数"""
    try:
        shangtext.insert_one({'projectname': projectname, 'text': text})
        logging.info(f"✅ 插入 shangtext：{projectname}")
    except Exception as e:
        logging.error(f"❌ 插入 shangtext 失败：{projectname} - {e}")

def sifatuwen(bot_id, projectname, text, file_id, key_text, keyboard, send_type):
    """司法图文插入函数"""
    try:
        sftw.insert_one({
            'bot_id': bot_id,
            'projectname': projectname,
            'text': text,
            'file_id': file_id,
            'key_text': key_text,
            'keyboard': keyboard,
            'send_type': send_type,
            'state': 1,
            'entities': b'\x80\x03]q\x00.'
        })
        logging.info(f"✅ 插入司法图文：{projectname}")
    except Exception as e:
        logging.error(f"❌ 插入司法图文失败：{projectname} - {e}")

def fanyibao(projectname, text, fanyi):
    """翻译包插入函数"""
    try:
        fyb.insert_one({
            'projectname': projectname,
            'text': text,
            'fanyi': fanyi
        })
        logging.info(f"✅ 插入翻译包：{projectname}")
    except Exception as e:
        logging.error(f"❌ 插入翻译包失败：{projectname} - {e}")

def goumaijilua(leixing, bianhao, user_id, projectname, text, ts, timer, count):
    """购买记录插入函数"""
    try:
        gmjlu.insert_one({
            'leixing': leixing,
            'bianhao': bianhao,
            'user_id': user_id,
            'projectname': projectname,
            'text': text,
            'ts': ts,
            'timer': timer,
            'count': count   # ✅ 记录实际数量
        })
        logging.info(f"✅ 插入购买记录：{user_id} - {projectname}")
    except Exception as e:
        logging.error(f"❌ 插入购买记录失败：{user_id} - {projectname} - {e}")

def xieyihaobaocun(uid, nowuid, hbid, projectname, timer):
    """协议号保存函数"""
    try:
        xyh.insert_one({
            'uid': uid,
            'nowuid': nowuid,
            'hbid': hbid,
            'projectname': projectname,
            'state': 0,
            'timer': timer
        })
        logging.info(f"✅ 保存协议号：{projectname} (nowuid={nowuid})")
    except Exception as e:
        logging.error(f"❌ 保存协议号失败：{projectname} - {e}")


def shangchuanhaobao(leixing, uid, nowuid, hbid, projectname, timer, remark=''):
    """优化的商品上架函数"""
    try:
        # 插入商品数据
        hb.insert_one({
            'leixing': leixing,
            'uid': uid,
            'nowuid': nowuid,
            'hbid': hbid,
            'projectname': projectname,
            'state': 0,
            'timer': timer,
            'remark': remark
        })
        logging.info(f"✅ 上架商品成功：{projectname} (nowuid={nowuid})")

        # ✅ 使用优化的库存通知管理器
        stock_manager.schedule_notification(nowuid, projectname)

    except Exception as e:
        logging.error(f"❌ 上架商品失败：{projectname} - {e}")




    
    
def erjifenleibiao(uid, nowuid, projectname, row):
    ejfl.insert_one({
        'uid': uid,
        'nowuid': nowuid,
        'projectname': projectname,
        'row': row,
        'text': f'''
<b>✅您的账户已打包完成，请查收！</b>

<b>🔐二级密码:请在json文件中【two2fa】查看！</b>

<b>⚠️注意：请马上检查账户，1小时内出现问题，联系客服处理！</b>
<b>‼️超过售后时间，损失自付，无需多言！</b>

<b>🔹 9号客服  @o9eth   @o7eth</b>
<b>🔹 频道  @idclub9999</b>
<b>🔹补货通知  @p5540</b>
        ''',
        'money': 0
    })


def fenleibiao(uid, projectname,row):
    fenlei.insert_one({
        'uid': uid,
        'projectname': projectname,
        'row': row
    })

def user_logging(uid, projectname , user_id, today_money, today_time):
    log_data = {
        'uid': uid,
        'projectname': projectname,
        'user_id': user_id,
        'today_money': today_money,
        'today_time': today_time,
        'log_time': datetime.now()
    }
    try:
        user_log.insert_one(log_data)
        print(f"✅ 日志已记录: {log_data}")
        logging.info(f"日志已记录: {log_data}")
    except Exception as e:
        error_msg = f"❌ 日志记录失败: {e}"
        print(error_msg)
        logging.error(error_msg)

def sydata(tranhash):
    """使用数据插入函数"""
    try:
        shiyong.insert_one({'tranhash': tranhash})
        logging.info(f"✅ 插入使用数据：{tranhash}")
    except Exception as e:
        logging.error(f"❌ 插入使用数据失败：{tranhash} - {e}")

def kehuduanurl(api, key):
    """客户端URL插入函数"""
    try:
        get_kehuduan.insert_one({
            'api': api,
            'key': key,
            'tcid': 0,
        })
        logging.info(f"✅ 插入客户端URL：{api}")
    except Exception as e:
        logging.error(f"❌ 插入客户端URL失败：{api} - {e}")

# ✅ 新增：实用工具函数
def get_product_stock(nowuid: str) -> int:
    """获取商品库存数量"""
    try:
        return hb.count_documents({'nowuid': nowuid, 'state': 0})
    except Exception as e:
        logging.error(f"❌ 获取库存失败：nowuid={nowuid} - {e}")
        return 0

def get_user_info(user_id: int) -> dict:
    """获取用户信息"""
    try:
        return user.find_one({'user_id': user_id}) or {}
    except Exception as e:
        logging.error(f"❌ 获取用户信息失败：user_id={user_id} - {e}")
        return {}

def update_user_balance(user_id: int, amount: float, balance_type: str = 'USDT') -> bool:
    """更新用户余额"""
    try:
        result = user.update_one(
            {'user_id': user_id},
            {'$inc': {balance_type: amount}}
        )
        if result.modified_count > 0:
            logging.info(f"✅ 更新用户余额：user_id={user_id}, {balance_type}+={amount}")
            return True
        else:
            logging.warning(f"⚠️ 用户余额更新无变化：user_id={user_id}")
            return False
    except Exception as e:
        logging.error(f"❌ 更新用户余额失败：user_id={user_id} - {e}")
        return False
    
    
def keybutton(Row, first):
    """按钮模板插入函数"""
    try:
        get_key.insert_one({
            'Row': Row,
            'first': first,
            'projectname': '点击修改内容',
            'text': '',
            'file_id': '',
            'file_type': '',
            'key_text': '',
            'keyboard': b'\x80\x03]q\x00.',
            'entities': b'\x80\x03]q\x00.'
        })
        logging.info(f"✅ 插入按钮模板 Row={Row}, first={first}")
    except Exception as e:
        logging.error(f"❌ 插入按钮模板失败：{e}")
    
    
def user_data(key_id, user_id, username, fullname, lastname, state, creation_time, last_contact_time):
    try:
        user.insert_one({
            'count_id': key_id,
            'user_id': user_id,
            'username': username,
            'fullname': fullname,
            'lastname': lastname,
            'state': state,
            'creation_time': creation_time,
            'last_contact_time': last_contact_time,
            'USDT': 0,
            'zgje': 0,
            'zgsl': 0,
            'sign': 0,
            'lang': 'zh',
            'verified': False   # ✅ 添加这一行
        })
        logging.info(f"✅ 新增用户：{user_id} ({username})")
    except Exception as e:
        logging.error(f"❌ 用户写入失败：{user_id} - {e}")

if shangtext.find_one({}) is None:
    logging.info("🔧 初始化 shangtext 数据")
    fstext = '''
 💎本店业务💎 

飞机号，协议号,  直登号(tdata) 批发/零售 !
开通飞机会员,  能量租用&TRX兑换 , 老号老群老频道 !

❗️ 未使用过的本店商品的，请先少量购买测试，以免造成不必要的争执！谢谢合作！

❗️ 免责声明：本店所有商品，仅用于娱乐测试，不得用于违法活动！ 请遵守当地法律法规！

⚙️ /start   ⬅️点击命令打开底部菜单!
    '''.strip()
    shang_text('欢迎语', fstext)
    shang_text('欢迎语样式', b'\x80\x03]q\x00.')
    shang_text('充值地址', '')
    shang_text('营业状态', 1)
    logging.info("✅ shangtext 初始化完成")
# ================================ 多机器人分销系统数据表 ================================

# 代理机器人信息表
agent_bots = db_manager.bot_db["agent_bots"]

# 代理商品价格表
agent_product_prices = db_manager.bot_db["agent_product_prices"]

# 代理订单记录表
agent_orders = db_manager.bot_db["agent_orders"]

# 代理提现申请表
agent_withdrawals = db_manager.bot_db["agent_withdrawals"]

# 提现申请表（总部系统）
withdrawal_requests = db_manager.bot_db["withdrawal_requests"]

# ================================ 多机器人分销系统数据操作函数 ================================

def create_agent_bot_data(agent_bot_id, agent_name, agent_token, agent_username, owner_id, commission_rate, creation_time):
    """创建代理机器人信息"""
    try:
        agent_bots.insert_one({
            'agent_bot_id': agent_bot_id,           # 代理机器人唯一ID
            'agent_name': agent_name,               # 代理名称
            'agent_token': agent_token,             # 代理机器人Token
            'agent_username': agent_username,       # 代理机器人用户名 @xxx
            'owner_id': owner_id,                   # 总部管理员ID
            'commission_rate': commission_rate,     # 佣金比例%
            'status': 'active',                     # 状态: active/inactive/suspended
            'creation_time': creation_time,         # 创建时间
            'last_sync_time': '',                   # 最后同步时间
            'total_users': 0,                       # 代理机器人用户总数
            'total_sales': 0.0,                     # 总销售额
            'total_commission': 0.0,                # 总佣金
            'available_balance': 0.0,               # 可提现余额
            'withdrawn_amount': 0.0,                # 已提现金额
            'settings': {
                'welcome_message': '',              # 自定义欢迎语
                'customer_service': '',             # 客服联系方式
                'auto_delivery': True,              # 自动发货
                'allow_recharge': True,             # 允许充值
                'min_purchase': 0.0,                # 最小购买金额
            }
        })
        logging.info(f"✅ 创建代理机器人成功：{agent_name} (@{agent_username})")
        return True
    except Exception as e:
        logging.error(f"❌ 创建代理机器人失败：{agent_name} - {e}")
        return False

def create_agent_product_price_data(agent_bot_id, original_nowuid, agent_price, is_active):
    """创建代理商品价格"""
    try:
        agent_product_prices.insert_one({
            'agent_bot_id': agent_bot_id,           # 代理机器人ID
            'original_nowuid': original_nowuid,     # 总部商品nowuid
            'agent_price': agent_price,             # 代理设置的价格
            'is_active': is_active,                 # 是否启用销售
            'sales_count': 0,                       # 销售数量
            'total_revenue': 0.0,                   # 总收入
            'last_sale_time': '',                   # 最后销售时间
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        logging.info(f"✅ 创建代理商品价格：agent_bot_id={agent_bot_id}, nowuid={original_nowuid}")
        return True
    except Exception as e:
        logging.error(f"❌ 创建代理商品价格失败：{e}")
        return False

def create_agent_order_data(order_id, agent_bot_id, customer_id, original_nowuid, quantity, 
                           agent_price, cost_price, profit, commission, order_time):
    """
    创建代理订单记录
    
    Args:
        order_time: 订单时间，必须为datetime对象（不是字符串）
    """
    try:
        agent_orders.insert_one({
            'order_id': order_id,                   # 订单ID
            'agent_bot_id': agent_bot_id,           # 代理机器人ID
            'customer_id': customer_id,             # 客户ID（在代理机器人中的ID）
            'original_nowuid': original_nowuid,     # 原始商品nowuid
            'quantity': quantity,                   # 购买数量
            'agent_price': agent_price,             # 代理售价
            'cost_price': cost_price,               # 成本价
            'profit': profit,                       # 利润
            'commission': commission,               # 代理佣金
            'status': 'completed',                  # 订单状态
            'order_time': order_time,               # 订单时间
            'delivery_content': '',                 # 发货内容
        })
        logging.info(f"✅ 创建代理订单：order_id={order_id}, agent_bot_id={agent_bot_id}")
        return True
    except Exception as e:
        logging.error(f"❌ 创建代理订单失败：{e}")
        return False

def create_agent_withdrawal_data(withdrawal_id, agent_bot_id, amount, payment_method, 
                                payment_account, status, apply_time):
    """创建代理提现申请"""
    try:
        agent_withdrawals.insert_one({
            'withdrawal_id': withdrawal_id,         # 提现ID
            'agent_bot_id': agent_bot_id,           # 代理机器人ID
            'amount': amount,                       # 提现金额
            'payment_method': payment_method,       # 提现方式
            'payment_account': payment_account,     # 收款账户
            'status': status,                       # pending/approved/rejected/completed
            'apply_time': apply_time,               # 申请时间
            'process_time': '',                     # 处理时间
            'process_by': '',                       # 处理人
            'notes': '',                            # 备注
        })
        logging.info(f"✅ 创建提现申请：withdrawal_id={withdrawal_id}, agent_bot_id={agent_bot_id}")
        return True
    except Exception as e:
        logging.error(f"❌ 创建提现申请失败：{e}")
        return False

# ================================ 代理机器人独立用户系统函数 ================================

def get_agent_bot_user_collection(agent_bot_id):
    """获取代理机器人的独立用户集合"""
    collection_name = f"agent_{agent_bot_id}_users"
    return db_manager.bot_db[collection_name]

def get_agent_bot_topup_collection(agent_bot_id):
    """获取代理机器人的独立充值记录集合"""
    collection_name = f"agent_{agent_bot_id}_topup"
    return db_manager.bot_db[collection_name]

def get_agent_bot_gmjlu_collection(agent_bot_id):
    """获取代理机器人的独立购买记录集合"""
    collection_name = f"agent_{agent_bot_id}_gmjlu"
    return db_manager.bot_db[collection_name]

def create_agent_user_data(agent_bot_id, user_id, username, fullname, creation_time):
    """在代理机器人中创建独立用户"""
    try:
        agent_users = get_agent_bot_user_collection(agent_bot_id)
        
        # 获取该代理机器人的最大count_id
        last_user = agent_users.find_one(sort=[('count_id', -1)])
        count_id = (last_user['count_id'] if last_user else 0) + 1
        
        agent_users.insert_one({
            'count_id': count_id,                   # 代理内部用户编号
            'user_id': user_id,                     # Telegram用户ID
            'username': username,                   # 用户名
            'fullname': fullname,                   # 全名
            'USDT': 0.0,                           # USDT余额（完全独立）
            'state': '1',                          # 状态
            'lang': 'zh',                          # 语言
            'creation_time': creation_time,         # 创建时间
            'zgje': 0.0,                           # 总购金额
            'zgsl': 0,                             # 总购数量
            'sign': 0,                             # 签到
            'last_contact_time': creation_time,     # 最后联系时间
            'verified': False,                     # 是否验证
        })
        
        logging.info(f"✅ 代理机器人创建用户：agent_bot_id={agent_bot_id}, user_id={user_id}")
        return True, count_id
    except Exception as e:
        logging.error(f"❌ 代理机器人创建用户失败：{e}")
        return False, 0

def get_agent_bot_user(agent_bot_id, user_id):
    """获取代理机器人用户信息"""
    try:
        agent_users = get_agent_bot_user_collection(agent_bot_id)
        return agent_users.find_one({'user_id': user_id})
    except Exception as e:
        logging.error(f"❌ 获取代理用户失败：{e}")
        return None

def update_agent_bot_user_balance(agent_bot_id, user_id, amount, balance_type='USDT'):
    """更新代理机器人用户余额（独立系统）"""
    try:
        agent_users = get_agent_bot_user_collection(agent_bot_id)
        result = agent_users.update_one(
            {'user_id': user_id},
            {'$inc': {balance_type: amount}}
        )
        if result.modified_count > 0:
            logging.info(f"✅ 更新代理用户余额：agent_bot_id={agent_bot_id}, user_id={user_id}, {balance_type}+={amount}")
            return True
        return False
    except Exception as e:
        logging.error(f"❌ 更新代理用户余额失败：{e}")
        return False

# ================================ 工具函数 ================================

def get_agent_bot_info(agent_bot_id):
    """获取代理机器人信息"""
    try:
        return agent_bots.find_one({'agent_bot_id': agent_bot_id})
    except Exception as e:
        logging.error(f"❌ 获取代理机器人信息失败：{e}")
        return None

def get_agent_product_price(agent_bot_id, original_nowuid):
    """获取代理商品价格"""
    try:
        return agent_product_prices.find_one({
            'agent_bot_id': agent_bot_id,
            'original_nowuid': original_nowuid,
            'is_active': True
        })
    except Exception as e:
        logging.error(f"❌ 获取代理商品价格失败：{e}")
        return None

def get_real_time_stock(original_nowuid):
    """获取实时库存（从总部）"""
    try:
        return hb.count_documents({'nowuid': original_nowuid, 'state': 0})
    except Exception as e:
        logging.error(f"❌ 获取实时库存失败：{e}")
        return 0

def generate_agent_bot_id():
    """生成代理机器人唯一ID"""
    import uuid
    import time
    timestamp = str(int(time.time()))[-8:]
    random_part = str(uuid.uuid4()).replace('-', '')[:16]
    return f"agent_{timestamp}{random_part}"

def get_agent_stats(agent_bot_id, period='all'):
    """
    获取代理机器人统计数据
    
    Args:
        agent_bot_id: 代理机器人ID
        period: 时间周期 '7d'|'17d'|'30d'|'90d'|'all'
        
    Returns:
        dict: 统计数据字典
        {
            'total_sales': float,          # 总销售额（周期内）
            'order_count': int,            # 订单数量（周期内）
            'avg_order': float,            # 平均订单额
            'total_commission': float,     # 总佣金（周期内）
            'profit_rate': float,          # 利润率%
            'withdrawn_amount': float,     # 已提现总额（全部时间）
            'available_balance': float,    # 可提现余额
            'pending_withdrawal_count': int,     # 待处理提现数量
            'pending_withdrawal_amount': float,  # 待处理提现金额
            'total_users': int            # 用户数量
        }
    """
    try:
        logging.info(f"🔍 get_agent_stats called for agent_bot_id: {agent_bot_id}, period: {period}")
        
        # 计算时间范围
        time_filter = {}
        if period != 'all':
            period_days = {
                '7d': 7,
                '17d': 17,
                '30d': 30,
                '90d': 90
            }
            days = period_days.get(period, 30)
            start_time = datetime.now() - timedelta(days=days)
            # 使用datetime过滤
            time_filter = {'order_time': {'$gte': start_time}}
            logging.info(f"📅 Time filter: orders since {start_time}")
        
        # 1. 从 agent_orders 聚合订单数据
        order_pipeline = [
            {'$match': {
                'agent_bot_id': agent_bot_id,
                'status': 'completed',
                **time_filter
            }},
            {'$group': {
                '_id': None,
                'total_sales': {
                    '$sum': {
                        '$multiply': [
                            {'$ifNull': ['$agent_price', 0]},
                            {'$ifNull': ['$quantity', 0]}
                        ]
                    }
                },
                'total_commission': {
                    '$sum': {'$ifNull': ['$commission', 0]}
                },
                'order_count': {'$sum': 1}
            }}
        ]
        
        order_result = list(agent_orders.aggregate(order_pipeline))
        order_stats = order_result[0] if order_result else {
            'total_sales': 0.0,
            'total_commission': 0.0,
            'order_count': 0
        }
        
        logging.info(f"📊 Orders stats - Sales: {order_stats['total_sales']}, Commission: {order_stats['total_commission']}, Orders: {order_stats['order_count']}")
        
        # 2. 计算全部时间的总佣金（用于可提现余额计算）
        all_time_commission_pipeline = [
            {'$match': {
                'agent_bot_id': agent_bot_id,
                'status': 'completed'
            }},
            {'$group': {
                '_id': None,
                'all_time_commission': {
                    '$sum': {'$ifNull': ['$commission', 0]}
                }
            }}
        ]
        
        all_commission_result = list(agent_orders.aggregate(all_time_commission_pipeline))
        all_time_commission = all_commission_result[0]['all_time_commission'] if all_commission_result else 0.0
        
        # 3. 获取已提现金额（全部时间，status='completed'）
        withdrawn_pipeline = [
            {'$match': {
                'agent_bot_id': agent_bot_id,
                'status': 'completed'
            }},
            {'$group': {
                '_id': None,
                'withdrawn_amount': {'$sum': '$amount'}
            }}
        ]
        
        withdrawn_result = list(agent_withdrawals.aggregate(withdrawn_pipeline))
        withdrawn_amount = withdrawn_result[0]['withdrawn_amount'] if withdrawn_result else 0.0
        
        logging.info(f"💰 Withdrawn: {withdrawn_amount}, All-time commission: {all_time_commission}")
        
        # 4. 获取待处理提现数据
        pending_withdrawals = list(agent_withdrawals.find({
            'agent_bot_id': agent_bot_id,
            'status': 'pending'
        }))
        pending_withdrawal_count = len(pending_withdrawals)
        pending_withdrawal_amount = sum(w.get('amount', 0) for w in pending_withdrawals)
        
        # 5. 获取用户数量
        agent_users_collection = get_agent_bot_user_collection(agent_bot_id)
        try:
            total_users = agent_users_collection.count_documents({})
        except:
            total_users = 0
        
        logging.info(f"👥 Total users: {total_users}")
        
        # 6. 计算派生指标
        total_sales = float(order_stats['total_sales'])
        total_commission = float(order_stats['total_commission'])
        order_count = int(order_stats['order_count'])
        
        # 平均订单额
        avg_order = total_sales / order_count if order_count > 0 else 0.0
        
        # 利润率
        profit_rate = (total_commission / total_sales * 100) if total_sales > 0 else 0.0
        
        # 可提现余额 = 全部时间累计佣金 - 已提现金额
        available_balance = all_time_commission - withdrawn_amount
        
        # 7. 兼容性：如果没有commission字段的旧订单，尝试从agent_bots获取commission_rate回退计算
        if total_commission == 0 and total_sales > 0:
            agent_info = agent_bots.find_one({'agent_bot_id': agent_bot_id})
            if agent_info and 'commission_rate' in agent_info:
                commission_rate = float(agent_info['commission_rate']) / 100
                total_commission = total_sales * commission_rate
                all_time_commission = total_commission
                available_balance = all_time_commission - withdrawn_amount
                profit_rate = agent_info['commission_rate']
                logging.info(f"⚠️ 代理 {agent_bot_id} 使用commission_rate回退计算佣金")
        
        # 8. 回退：如果agent_orders为空，尝试从旧的agent_{id}_gmjlu集合读取（兼容历史数据）
        if order_count == 0:
            try:
                agent_gmjlu = get_agent_bot_gmjlu_collection(agent_bot_id)
                if agent_gmjlu is not None:
                    match_filter = {'leixing': 'purchase'}
                    if period != 'all':
                        period_days = {'7d': 7, '17d': 17, '30d': 30, '90d': 90}
                        days = period_days.get(period, 30)
                        start_time = datetime.now() - timedelta(days=days)
                        start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
                        match_filter['timer'] = {'$gte': start_time_str}
                    
                    fallback_pipeline = [
                        {'$match': match_filter},
                        {'$group': {
                            '_id': None,
                            'total_sales': {'$sum': '$ts'},
                            'order_count': {'$sum': 1}
                        }}
                    ]
                    fallback_result = list(agent_gmjlu.aggregate(fallback_pipeline))
                    if fallback_result:
                        total_sales = float(fallback_result[0].get('total_sales', 0))
                        order_count = fallback_result[0].get('order_count', 0)
                        avg_order = total_sales / order_count if order_count > 0 else 0.0
                        
                        # 使用commission_rate计算
                        agent_info = agent_bots.find_one({'agent_bot_id': agent_bot_id})
                        if agent_info and 'commission_rate' in agent_info:
                            commission_rate = float(agent_info['commission_rate']) / 100
                            total_commission = total_sales * commission_rate
                            profit_rate = agent_info['commission_rate']
                            
                            # 计算全部时间销售额用于余额
                            if period != 'all':
                                all_sales_pipeline = [
                                    {'$match': {'leixing': 'purchase'}},
                                    {'$group': {'_id': None, 'total_sales': {'$sum': '$ts'}}}
                                ]
                                all_sales_result = list(agent_gmjlu.aggregate(all_sales_pipeline))
                                all_time_sales = float(all_sales_result[0].get('total_sales', 0)) if all_sales_result else 0.0
                                all_time_commission = all_time_sales * commission_rate
                            else:
                                all_time_commission = total_commission
                            
                            available_balance = all_time_commission - withdrawn_amount
                            logging.info(f"⚠️ 使用旧gmjlu集合回退数据：sales={total_sales}, orders={order_count}")
            except Exception as e:
                logging.warning(f"⚠️ 旧数据回退失败: {e}")
        
        result = {
            'total_sales': round(total_sales, 2),
            'order_count': order_count,
            'avg_order': round(avg_order, 2),
            'total_commission': round(total_commission, 2),
            'profit_rate': round(profit_rate, 2),
            'withdrawn_amount': round(withdrawn_amount, 2),
            'available_balance': round(available_balance, 2),
            'pending_withdrawal_count': pending_withdrawal_count,
            'pending_withdrawal_amount': round(pending_withdrawal_amount, 2),
            'total_users': total_users,
            'period': period
        }
        
        logging.info(f"✅ get_agent_stats returning: {result}")
        return result
        
    except Exception as e:
        logging.error(f"❌ 获取代理统计失败：agent_bot_id={agent_bot_id}, period={period}, error={e}")
        import traceback
        traceback.print_exc()
        # 返回安全的全0结构
        return {
            'total_sales': 0.0,
            'order_count': 0,
            'avg_order': 0.0,
            'total_commission': 0.0,
            'profit_rate': 0.0,
            'withdrawn_amount': 0.0,
            'available_balance': 0.0,
            'pending_withdrawal_count': 0,
            'pending_withdrawal_amount': 0.0,
            'total_users': 0,
            'period': period
        }

# ================================ 初始化多机器人分销系统 ================================

def init_multi_bot_distribution_system():
    """初始化多机器人分销系统"""
    try:
        # 创建索引以提高查询性能
        agent_bots.create_index("agent_bot_id", unique=True)
        agent_bots.create_index("agent_token", unique=True)
        agent_bots.create_index([("status", 1), ("creation_time", -1)])
        
        agent_product_prices.create_index([("agent_bot_id", 1), ("original_nowuid", 1), ("is_active", 1)])
        agent_orders.create_index([("agent_bot_id", 1), ("order_time", -1)])
        agent_withdrawals.create_index([("agent_bot_id", 1), ("status", 1)])
        
        # 总部提现申请表索引
        withdrawal_requests.create_index([("user_id", 1), ("status", 1)])
        withdrawal_requests.create_index([("status", 1), ("created_time", -1)])
        
        logging.info("✅ 多机器人分销系统初始化完成")
        return True
    except Exception as e:
        logging.error(f"❌ 多机器人分销系统初始化失败：{e}")
        return False

# 初始化系统
init_multi_bot_distribution_system()

print("🤖 多机器人分销系统数据表加载完成")
if __name__ == '__main__':
      pass
    
