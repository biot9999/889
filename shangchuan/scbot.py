import os
import re
import json
import uuid
import time
import zipfile
import logging
import hashlib
import threading
import shutil
from datetime import datetime
from glob import glob
from pathlib import Path
from dotenv import load_dotenv

import telegram
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, 
    CommandHandler, 
    CallbackContext, 
    MessageHandler, 
    CallbackQueryHandler,
    Filters
)

from pymongo import MongoClient
from collections import defaultdict

# 加载环境变量
load_dotenv()

# 配置
UPLOAD_BOT_TOKEN = os.getenv("UPLOAD_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "bot_database")
ADMIN_IDS = list(map(int, filter(None, os.getenv("ADMIN_IDS", "").split(","))))

# 🔥 补货通知配置
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv('BOT_USERNAME', 'session9haobot')
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", "0"))
ENABLE_NOTIFICATIONS = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"

# 主机器人路径配置
MAIN_BOT_PATH = os.getenv("MAIN_BOT_PATH", "/root")
PROTOCOL_PATH = os.path.join(MAIN_BOT_PATH, "协议号")
PACKAGE_PATH = os.path.join(MAIN_BOT_PATH, "号包")

# 日志配置
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('upload_bot.log'),
        logging.StreamHandler()
    ]
)

# MongoDB连接
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    ejfl = db['ejfl']
    hb = db['hb']
    fenlei = db['fenlei']
    
    logging.info("✅ MongoDB连接成功")
except Exception as e:
    logging.error(f"❌ MongoDB连接失败: {e}")
    exit(1)

# 🔥 初始化通知机器人
notification_bot = None
if BOT_TOKEN and ENABLE_NOTIFICATIONS and NOTIFY_CHANNEL_ID != 0:
    try:
        notification_bot = telegram.Bot(token=BOT_TOKEN)
        logging.info("✅ 通知机器人初始化成功")
        logging.info(f"📢 通知频道ID: {NOTIFY_CHANNEL_ID}")
    except Exception as e:
        logging.error(f"❌ 通知机器人初始化失败: {e}")

def create_directories():
    dirs = [
        'upload_temp',
        'duplicate_files', 
        'processed_files',
        PROTOCOL_PATH,
        PACKAGE_PATH
    ]
    
    for dir_name in dirs:
        try:
            os.makedirs(dir_name, exist_ok=True)
            logging.info(f"📁 创建/验证目录: {dir_name}")
        except Exception as e:
            logging.error(f"❌ 创建目录失败 {dir_name}: {e}")

def generate_24bit_uid():
    uid = uuid.uuid4()
    uid_str = str(uid)
    hashed_uid = hashlib.md5(uid_str.encode()).hexdigest()
    return hashed_uid[:24]

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_all_categories():
    categories = {}
    try:
        for category in ejfl.find():
            name = category.get('projectname', '')
            if name and name != '点击按钮修改':
                categories[name] = {
                    'nowuid': category.get('nowuid'),
                    'uid': category.get('uid'),
                    'name': name
                }
        logging.info(f"📋 获取到 {len(categories)} 个商品分类")
        return categories
    except Exception as e:
        logging.error(f"❌ 获取分类失败: {e}")
        return {}

def check_duplicate_files(file_names, nowuid):
    duplicates = []
    new_files = []
    
    try:
        for file_name in file_names:
            if hb.find_one({'nowuid': nowuid, 'projectname': file_name}):
                duplicates.append(file_name)
                logging.warning(f"🔄 发现重复文件: {file_name}")
            else:
                new_files.append(file_name)
                
        logging.info(f"📊 文件检查结果 - 新文件: {len(new_files)}, 重复文件: {len(duplicates)}")
        return new_files, duplicates
        
    except Exception as e:
        logging.error(f"❌ 检查重复文件失败: {e}")
        return file_names, []

# 🔥 新格式的库存通知函数
def send_stock_notification(nowuid: str, new_count: int):
    """发送库存更新通知 - 使用新的格式"""
    if not notification_bot or not ENABLE_NOTIFICATIONS or NOTIFY_CHANNEL_ID == 0:
        logging.info("📢 库存通知功能未启用或配置不完整")
        return
    
    try:
        if new_count <= 0:
            logging.info(f"ℹ️ 补货数为0，跳过通知：nowuid={nowuid}")
            return
        
        logging.info(f"🔔 开始发送库存通知：nowuid={nowuid}, new_count={new_count}")
        
        # 获取二级分类信息
        product = ejfl.find_one({'nowuid': nowuid})
        if not product:
            logging.warning(f"❌ 未找到商品信息：nowuid={nowuid}")
            return
        
        logging.info(f"📦 找到商品信息：{product.get('projectname', '未知')}")
        
        # 获取一级分类信息
        uid = product.get('uid')
        parent_category = fenlei.find_one({'uid': uid})
        parent_name = parent_category['projectname'] if parent_category else "未知分类"
        product_name = product['projectname']
        
        logging.info(f"📂 一级分类：{parent_name}, 二级分类：{product_name}")
        
        # 获取价格和当前库存
        price = float(product.get('money', 0))
        current_stock = hb.count_documents({'nowuid': nowuid, 'state': 0})
        
        logging.info(f"💰 价格：{price} U, 📊 当前库存：{current_stock}")
        
        # 🔥 使用您要求的新通知格式
        text = f"""<b>💭💭 库存更新💭💭</b>

<b>{parent_name} /{product_name}</b>

<b>💰 商品价格：{price:.2f} U</b>

<b>🆕 新增库存：{new_count} 个</b>

<b>📊 剩余库存：{current_stock} 个</b>

<b>🛒 点击下方按钮快速购买</b>"""

        # 创建购买按钮
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 购买商品", url=f"https://t.me/{BOT_USERNAME}?start=buy_{nowuid}")]
        ])
        
        logging.info(f"📝 通知消息构建完成，准备发送到频道：{NOTIFY_CHANNEL_ID}")
        
        # 发送到通知频道
        notification_bot.send_message(
            chat_id=NOTIFY_CHANNEL_ID, 
            text=text, 
            parse_mode='HTML', 
            reply_markup=keyboard
        )
        
        logging.info(f"✅ 库存通知发送成功：{parent_name}/{product_name} (新增{new_count}个)")
        
    except Exception as e:
        logging.error(f"❌ 库存通知发送失败：{e}")
        import traceback
        logging.error(f"📋 详细错误信息：{traceback.format_exc()}")

def upload_to_database(nowuid, uid, file_names, file_type='协议号'):
    success_count = 0
    timer = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        for file_name in file_names:
            hbid = generate_24bit_uid()
            
            hb_data = {
                'hbid': hbid,
                'uid': uid,
                'nowuid': nowuid,
                'projectname': file_name,
                'leixing': file_type,
                'state': 0,
                'timer': timer
            }
            
            hb.insert_one(hb_data)
            success_count += 1
            logging.info(f"✅ 数据库记录创建: {file_name}")
            
        logging.info(f"🎉 批量上传完成，成功上传 {success_count} 个文件")
        
        # 🔥 发送库存更新通知
        if success_count > 0:
            logging.info(f"📢 准备发送通知：nowuid={nowuid}, success_count={success_count}")
            send_stock_notification(nowuid, success_count)
        
        return success_count
        
    except Exception as e:
        logging.error(f"❌ 数据库上传失败: {e}")
        return 0

def process_session_files(zip_path, category_info):
    nowuid = category_info['nowuid']
    uid = category_info['uid']
    category_name = category_info['name']
    
    extract_path = f"upload_temp/{nowuid}_{int(time.time())}"
    os.makedirs(extract_path, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
            
            session_files = glob(f"{extract_path}/**/*.session", recursive=True)
            json_files = glob(f"{extract_path}/**/*.json", recursive=True)
            
            all_files = set()
            for file_path in session_files + json_files:
                base_name = Path(file_path).stem
                all_files.add(base_name)
            
            file_names = list(all_files)
            
            if not file_names:
                return 0, 0, "未找到有效的session或json文件"
            
            new_files, duplicates = check_duplicate_files(file_names, nowuid)
            
            if new_files:
                target_dir = os.path.join(PROTOCOL_PATH, nowuid)
                os.makedirs(target_dir, exist_ok=True)
                
                logging.info(f"📂 目标目录: {target_dir}")
                
                copied_files = []
                for file_name in new_files:
                    session_copied = False
                    json_copied = False
                    
                    for session_file in session_files:
                        if Path(session_file).stem == file_name:
                            dst_session = os.path.join(target_dir, f"{file_name}.session")
                            try:
                                shutil.copy2(session_file, dst_session)
                                os.chmod(dst_session, 0o644)
                                session_copied = True
                                logging.info(f"📁 Session文件复制: {session_file} -> {dst_session}")
                            except Exception as e:
                                logging.error(f"❌ 复制session文件失败: {e}")
                            break
                    
                    for json_file in json_files:
                        if Path(json_file).stem == file_name:
                            dst_json = os.path.join(target_dir, f"{file_name}.json")
                            try:
                                shutil.copy2(json_file, dst_json)
                                os.chmod(dst_json, 0o644)
                                json_copied = True
                                logging.info(f"📁 JSON文件复制: {json_file} -> {dst_json}")
                            except Exception as e:
                                logging.error(f"❌ 复制json文件失败: {e}")
                            break
                    
                    if session_copied or json_copied:
                        copied_files.append(file_name)
                    else:
                        logging.warning(f"⚠️ 文件 {file_name} 未找到对应的session或json文件")
                
                if copied_files:
                    success_count = upload_to_database(nowuid, uid, copied_files, '协议号')
                    return success_count, len(duplicates), "处理完成"
                else:
                    return 0, len(duplicates), "没有文件被成功复制"
            
        return 0, len(duplicates), "没有新文件需要处理"
        
    except Exception as e:
        error_msg = f"处理协议号文件失败: {e}"
        logging.error(f"❌ {error_msg}")
        return 0, 0, error_msg
    
    finally:
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path)

def process_tdata_files(zip_path, category_info):
    nowuid = category_info['nowuid']
    uid = category_info['uid']
    category_name = category_info['name']
    
    extract_path = f"upload_temp/{nowuid}_{int(time.time())}"
    os.makedirs(extract_path, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
            
            tdata_accounts = []
            for root, dirs, files in os.walk(extract_path):
                if 'tdata' in dirs:
                    account_name = os.path.basename(root)
                    if account_name and account_name != os.path.basename(extract_path):
                        tdata_accounts.append(account_name)
                        logging.info(f"🔍 发现tdata账号: {account_name}")
            
            if not tdata_accounts:
                return 0, 0, "未找到有效的tdata文件夹结构"
            
            new_files, duplicates = check_duplicate_files(tdata_accounts, nowuid)
            
            if new_files:
                target_dir = os.path.join(PACKAGE_PATH, nowuid)
                os.makedirs(target_dir, exist_ok=True)
                
                logging.info(f"📂 目标目录: {target_dir}")
                
                copied_accounts = []
                for account_name in new_files:
                    src_account_dir = os.path.join(extract_path, account_name)
                    dst_account_dir = os.path.join(target_dir, account_name)
                    
                    if os.path.exists(src_account_dir) and os.path.isdir(src_account_dir):
                        try:
                            if os.path.exists(dst_account_dir):
                                shutil.rmtree(dst_account_dir)
                            
                            shutil.copytree(src_account_dir, dst_account_dir)
                            
                            for root, dirs, files in os.walk(dst_account_dir):
                                for d in dirs:
                                    os.chmod(os.path.join(root, d), 0o755)
                                for f in files:
                                    os.chmod(os.path.join(root, f), 0o644)
                            
                            copied_accounts.append(account_name)
                            logging.info(f"📁 账号目录复制: {src_account_dir} -> {dst_account_dir}")
                            
                        except Exception as e:
                            logging.error(f"❌ 复制账号目录失败 {account_name}: {e}")
                    else:
                        logging.warning(f"⚠️ 账号目录不存在: {src_account_dir}")
                
                if copied_accounts:
                    success_count = upload_to_database(nowuid, uid, copied_accounts, '直登号')
                    return success_count, len(duplicates), "处理完成"
                else:
                    return 0, len(duplicates), "没有账号目录被成功复制"
        
        return 0, len(duplicates), "没有新文件需要处理"
        
    except Exception as e:
        error_msg = f"处理tdata文件失败: {e}"
        logging.error(f"❌ {error_msg}")
        return 0, 0, error_msg
    
    finally:
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path)

def create_duplicate_package(duplicates, original_filename):
    if not duplicates:
        return None
    
    timestamp = int(time.time())
    duplicate_zip = f"duplicate_files/重复文件_{original_filename}_{timestamp}.zip"
    
    try:
        with zipfile.ZipFile(duplicate_zip, 'w') as zipf:
            duplicate_list = f"重复文件列表 ({len(duplicates)} 个):\n\n" + "\n".join(duplicates)
            zipf.writestr("重复文件列表.txt", duplicate_list)
            
        logging.info(f"📦 创建重复文件包: {duplicate_zip}")
        return duplicate_zip
        
    except Exception as e:
        logging.error(f"❌ 创建重复文件包失败: {e}")
        return None

def send_response(update: Update, text: str, reply_markup=None):
    """统一的响应发送函数，自动判断是消息还是回调查询"""
    try:
        if update.callback_query:
            update.callback_query.edit_message_text(
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        elif update.message:
            update.message.reply_text(
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
    except Exception as e:
        logging.error(f"❌ 发送响应失败: {e}")
        if update.callback_query:
            try:
                update.callback_query.message.reply_text(
                    text=text,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            except Exception as e2:
                logging.error(f"❌ 发送回调响应失败: {e2}")

def test_notification_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        send_response(update, "❌ 您没有权限使用此机器人")
        return
    
    if not notification_bot or not ENABLE_NOTIFICATIONS or NOTIFY_CHANNEL_ID == 0:
        send_response(update, "❌ 库存通知功能未启用或配置不正确")
        return
    
    try:
        test_product = ejfl.find_one({'projectname': {'$ne': '点击按钮修改'}})
        if test_product:
            nowuid = test_product['nowuid']
            
            logging.info(f"🧪 开始发送测试通知：nowuid={nowuid}")
            send_stock_notification(nowuid, 5)
            
            response_text = f"""✅ 测试库存通知已发送到频道！

📢 通知频道: <code>{NOTIFY_CHANNEL_ID}</code>
🤖 机器人用户名: <code>@{BOT_USERNAME}</code>
📦 测试商品: <code>{test_product['projectname']}</code>
🔗 测试链接: https://t.me/{BOT_USERNAME}?start=buy_{nowuid}

💭 使用新的通知格式：
<b>💭💭 库存更新💭💭</b>"""
            
            send_response(update, response_text)
        else:
            send_response(update, "❌ 未找到可用于测试的商品")
            
    except Exception as e:
        logging.error(f"❌ 测试通知失败: {e}")
        send_response(update, f"❌ 发送测试通知失败: {str(e)}")

def start_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        send_response(update, "❌ 您没有权限使用此机器人")
        return
    
    notification_status = "✅ 启用" if (notification_bot and ENABLE_NOTIFICATIONS and NOTIFY_CHANNEL_ID != 0) else "❌ 禁用"
    
    welcome_text = f"""
🤖 <b>批量上传机器人 v2.5 - 稳定版</b>

<b>📂 文件路径配置：</b>
• 协议号目录: <code>{PROTOCOL_PATH}</code>
• 号包目录: <code>{PACKAGE_PATH}</code>

<b>📢 库存通知配置：</b>
• 通知状态: {notification_status}
• 通知频道: <code>{NOTIFY_CHANNEL_ID if NOTIFY_CHANNEL_ID != 0 else '未配置'}</code>
• 机器人用户名: <code>@{BOT_USERNAME}</code>
• 💭 使用格式: <b>💭💭 库存更新💭💭</b>

<b>📋 使用说明：</b>
1️⃣ 发送ZIP压缩包文件
2️⃣ 文件名必须与商品二级分类名一致
3️⃣ 支持协议号(.session/.json)和tdata文件
4️⃣ 自动检测并过滤重复文件
5️⃣ 自动发送库存更新通知到频道📢

<b>🔧 可用命令：</b>
• /start - 显示帮助信息
• /categories - 查看所有商品分类
• /stats - 查看上传统计
• /path - 显示当前路径配置
• /test_notify - 测试库存通知功能

现在可以直接发送ZIP文件开始批量上传！
    """
    
    keyboard = [
        [InlineKeyboardButton("📋 查看分类", callback_data="show_categories")],
        [InlineKeyboardButton("📊 上传统计", callback_data="show_stats")],
        [InlineKeyboardButton("📂 路径配置", callback_data="show_paths")],
        [InlineKeyboardButton("📢 测试通知", callback_data="test_notification")]
    ]
    
    send_response(update, welcome_text, InlineKeyboardMarkup(keyboard))

def path_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        send_response(update, "❌ 您没有权限使用此机器人")
        return
    
    protocol_exists = os.path.exists(PROTOCOL_PATH)
    package_exists = os.path.exists(PACKAGE_PATH)
    notification_status = "✅ 正常" if (notification_bot and ENABLE_NOTIFICATIONS and NOTIFY_CHANNEL_ID != 0) else "❌ 未启用"
    
    path_text = f"""
📂 <b>系统配置信息</b>

<b>🔧 文件路径：</b>
• 主机器人根目录: <code>{MAIN_BOT_PATH}</code>
• 协议号存储路径: <code>{PROTOCOL_PATH}</code>
  状态: {"✅ 存在" if protocol_exists else "❌ 不存在"}
• 号包存储路径: <code>{PACKAGE_PATH}</code>
  状态: {"✅ 存在" if package_exists else "❌ 不存在"}

<b>📢 库存通知配置：</b>
• 通知功能: {notification_status}
• 主机器人Token: {'✅ 已配置' if BOT_TOKEN else '❌ 未配置'}
• 通知频道ID: <code>{NOTIFY_CHANNEL_ID if NOTIFY_CHANNEL_ID != 0 else '未配置'}</code>
• 机器人用户名: <code>@{BOT_USERNAME}</code>
• 💭 通知格式: <b>💭💭 库存更新💭💭</b>

<b>📊 目录统计：</b>
"""
    
    try:
        if protocol_exists:
            protocol_subdirs = len([d for d in os.listdir(PROTOCOL_PATH) 
                                 if os.path.isdir(os.path.join(PROTOCOL_PATH, d))])
            path_text += f"• 协议号分类目录: <code>{protocol_subdirs}</code> 个\n"
        
        if package_exists:
            package_subdirs = len([d for d in os.listdir(PACKAGE_PATH) 
                                if os.path.isdir(os.path.join(PACKAGE_PATH, d))])
            path_text += f"• 号包分类目录: <code>{package_subdirs}</code> 个\n"
            
    except Exception as e:
        path_text += f"❌ 获取目录统计失败: {e}\n"
    
    path_text += f"\n⏰ 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    keyboard = [
        [InlineKeyboardButton("🔄 刷新", callback_data="refresh_paths")],
        [InlineKeyboardButton("📢 测试通知", callback_data="test_notification")]
    ]
    
    send_response(update, path_text, InlineKeyboardMarkup(keyboard))

def categories_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        send_response(update, "❌ 您没有权限使用此机器人")
        return
    
    categories = get_all_categories()
    
    if not categories:
        send_response(update, "❌ 未找到任何商品分类")
        return
    
    page_size = 15
    text = "<b>📋 商品分类列表</b>\n\n"
    
    category_list = list(categories.items())[:page_size]
    for i, (name, info) in enumerate(category_list, 1):
        stock_count = hb.count_documents({'nowuid': info['nowuid'], 'state': 0})
        
        protocol_dir = os.path.join(PROTOCOL_PATH, info['nowuid'])
        package_dir = os.path.join(PACKAGE_PATH, info['nowuid'])
        
        status_icons = ""
        if os.path.exists(protocol_dir):
            status_icons += "📄"
        if os.path.exists(package_dir):
            status_icons += "📦"
        
        text += f"{i}. {status_icons} <code>{name}</code> (库存: {stock_count})\n"
    
    if len(categories) > page_size:
        text += f"\n📄 显示前{page_size}个，共{len(categories)}个分类"
    
    keyboard = [
        [InlineKeyboardButton("🔄 刷新", callback_data="refresh_categories")],
        [InlineKeyboardButton("📂 查看路径", callback_data="show_paths")]
    ]
    
    send_response(update, text, InlineKeyboardMarkup(keyboard))

def stats_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        send_response(update, "❌ 您没有权限使用此机器人")
        return
    
    try:
        total_stock = hb.count_documents({'state': 0})
        
        pipeline = [
            {'$match': {'state': 0}},
            {'$group': {'_id': '$nowuid', 'count': {'$sum': 1}}}
        ]
        category_stats = list(hb.aggregate(pipeline))
        
        today = datetime.now().strftime('%Y-%m-%d')
        today_uploads = hb.count_documents({
            'state': 0,
            'timer': {'$regex': f'^{today}'}
        })
        
        notification_status = "✅ 正常" if (notification_bot and ENABLE_NOTIFICATIONS and NOTIFY_CHANNEL_ID != 0) else "❌ 未启用"
        
        stats_text = f"""
📊 <b>系统统计信息</b>

<b>📋 库存统计：</b>
• 总库存数量：<code>{total_stock}</code>
• 商品分类：<code>{len(category_stats)}</code>  
• 今日上传：<code>{today_uploads}</code>

<b>📂 系统状态：</b>
• 协议号目录：{"✅" if os.path.exists(PROTOCOL_PATH) else "❌"}
• 号包目录：{"✅" if os.path.exists(PACKAGE_PATH) else "❌"}
• 库存通知：{notification_status}
• 💭 通知格式: <b>💭💭 库存更新💭💭</b>

<b>🔝 库存最多的分类：</b>
"""
        
        sorted_stats = sorted(category_stats, key=lambda x: x['count'], reverse=True)[:5]
        categories = get_all_categories()
        
        for i, stat in enumerate(sorted_stats, 1):
            nowuid = stat['_id']
            count = stat['count']
            category_name = "未知分类"
            
            for name, info in categories.items():
                if info['nowuid'] == nowuid:
                    category_name = name
                    break
            
            stats_text += f"{i}. {category_name}: <code>{count}</code>个\n"
        
        stats_text += f"\n⏰ 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        keyboard = [
            [InlineKeyboardButton("🔄 刷新统计", callback_data="refresh_stats")]
        ]
        
        send_response(update, stats_text, InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logging.error(f"❌ 获取统计信息失败: {e}")
        send_response(update, "❌ 获取统计信息失败，请稍后重试")

def handle_document(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("❌ 您没有权限使用此机器人")
        return
    
    document = update.message.document
    filename = document.file_name
    
    if not filename.lower().endswith('.zip'):
        update.message.reply_text("❌ 只支持ZIP格式的压缩包文件")
        return
    
    category_name = filename[:-4]
    categories = get_all_categories()
    
    # 🔥 简单的分类检查，不存在就直接报错
    if category_name not in categories:
        available_categories = list(categories.keys())[:10]
        error_text = f"❌ 未找到名为 '<code>{category_name}</code>' 的商品分类\n\n"
        error_text += "📋 可用的分类名称（前10个）：\n"
        for i, name in enumerate(available_categories, 1):
            error_text += f"{i}. <code>{name}</code>\n"
        
        if len(categories) > 10:
            error_text += f"\n还有 {len(categories) - 10} 个分类，使用 /categories 查看完整列表"
        
        update.message.reply_text(error_text, parse_mode='HTML')
        return
    
    category_info = categories[category_name]
    
    notification_enabled = notification_bot and ENABLE_NOTIFICATIONS and NOTIFY_CHANNEL_ID != 0
    
    processing_msg = update.message.reply_text(
        f"⏳ 正在处理文件: <code>{filename}</code>\n"
        f"📂 目标分类: <code>{category_name}</code>\n"
        f"🎯 分类ID: <code>{category_info['nowuid']}</code>\n"
        f"📢 库存通知: {'启用 💭💭' if notification_enabled else '禁用'}",
        parse_mode='HTML'
    )
    
    try:
        file_obj = context.bot.get_file(document.file_id)
        temp_file_path = f"upload_temp/{filename}"
        file_obj.download(temp_file_path)
        
        logging.info(f"📥 文件下载完成: {filename} ({os.path.getsize(temp_file_path)} 字节)")
        
        context.bot.edit_message_text(
            text=f"📥 文件下载完成，正在分析文件内容...\n"
                 f"📂 分类: <code>{category_name}</code>\n"
                 f"📁 大小: {os.path.getsize(temp_file_path)} 字节",
            chat_id=update.effective_chat.id,
            message_id=processing_msg.message_id,
            parse_mode='HTML'
        )
        
        with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            has_session = any(f.endswith('.session') or f.endswith('.json') for f in file_list)
            has_tdata = any('tdata' in f.lower() for f in file_list)
            
            logging.info(f"🔍 文件分析: session={has_session}, tdata={has_tdata}")
            
            if has_session:
                processed, duplicates, message = process_session_files(temp_file_path, category_info)
                file_type = "协议号"
                storage_path = os.path.join(PROTOCOL_PATH, category_info['nowuid'])
            elif has_tdata:
                processed, duplicates, message = process_tdata_files(temp_file_path, category_info)
                file_type = "tdata文件"
                storage_path = os.path.join(PACKAGE_PATH, category_info['nowuid'])
            else:
                processed, duplicates, message = 0, 0, "未识别的文件类型"
                storage_path = "未知"
        
        notification_sent = processed > 0 and notification_enabled
        
        result_text = f"""
✅ <b>文件处理完成</b>

📁 <b>文件信息：</b>
• 分类：<code>{category_name}</code>
• 类型：{file_type}

📊 <b>处理结果：</b>

• ✅ 新增：<code>{processed}</code> 个

• 🔄 重复：<code>{duplicates}</code> 个  

• 📝 状态：{message}

⏰ 处理时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        if duplicates > 0:
            duplicate_package = create_duplicate_package(
                [f"重复文件 {i+1}" for i in range(duplicates)], 
                filename[:-4]
            )
            result_text += f"\n⚠️ 发现 {duplicates} 个重复文件，已自动跳过"
            
            if duplicate_package:
                result_text += "\n📦 重复文件列表已打包"
        
        context.bot.edit_message_text(
            text=result_text,
            chat_id=update.effective_chat.id,
            message_id=processing_msg.message_id,
            parse_mode='HTML'
        )
        
        if duplicates > 0 and 'duplicate_package' in locals() and duplicate_package and os.path.exists(duplicate_package):
            with open(duplicate_package, 'rb') as f:
                context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    caption="📦 重复文件打包列表"
                )
        
        logging.info(f"🎉 处理完成: {filename} - 新增: {processed}, 重复: {duplicates}")
        
    except Exception as e:
        error_msg = f"❌ 处理文件失败: {str(e)}"
        logging.error(error_msg)
        
        context.bot.edit_message_text(
            text=f"❌ <b>处理失败</b>\n\n"
                 f"文件：<code>{filename}</code>\n"
                 f"错误：{str(e)}",
            chat_id=update.effective_chat.id,
            message_id=processing_msg.message_id,
            parse_mode='HTML'
        )
    
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def handle_callback_query(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    if not is_admin(user_id):
        query.edit_message_text("❌ 您没有权限使用此机器人")
        return
    
    try:
        if query.data == "show_categories":
            categories_command(update, context)
        elif query.data == "show_stats":
            stats_command(update, context)
        elif query.data == "show_paths":
            path_command(update, context)
        elif query.data == "test_notification":
            test_notification_command(update, context)
        elif query.data == "refresh_categories":
            categories_command(update, context)
        elif query.data == "refresh_stats":
            stats_command(update, context)
        elif query.data == "refresh_paths":
            path_command(update, context)
    except Exception as e:
        logging.error(f"❌ 处理回调查询失败: {e}")
        try:
            query.edit_message_text(f"❌ 操作失败: {str(e)}")
        except:
            pass

def main():
    logging.info("🔧 环境变量调试信息:")
    logging.info(f"BOT_TOKEN: {'已设置 (' + BOT_TOKEN[:10] + '...)' if BOT_TOKEN else '未设置'}")
    logging.info(f"BOT_USERNAME: {BOT_USERNAME}")
    logging.info(f"NOTIFY_CHANNEL_ID: {NOTIFY_CHANNEL_ID}")
    logging.info(f"ENABLE_NOTIFICATIONS: {ENABLE_NOTIFICATIONS}")
    
    logging.info(f"🚀 批量上传机器人启动...")
    logging.info(f"📂 协议号路径: {PROTOCOL_PATH}")
    logging.info(f"📦 号包路径: {PACKAGE_PATH}")
    
    notification_enabled = notification_bot and ENABLE_NOTIFICATIONS and NOTIFY_CHANNEL_ID != 0
    logging.info(f"📢 库存通知: {'启用 💭💭' if notification_enabled else '禁用'}")
    if notification_enabled:
        logging.info(f"📺 通知频道: {NOTIFY_CHANNEL_ID}")
        logging.info(f"🤖 机器人用户名: @{BOT_USERNAME}")
        logging.info(f"💭 通知格式: 💭💭 库存更新💭💭")
    else:
        logging.warning("⚠️ 库存通知未启用，请检查配置")
    
    create_directories()
    
    updater = Updater(token=UPLOAD_BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(CommandHandler('categories', categories_command))
    dispatcher.add_handler(CommandHandler('stats', stats_command))
    dispatcher.add_handler(CommandHandler('path', path_command))
    dispatcher.add_handler(CommandHandler('test_notify', test_notification_command))
    dispatcher.add_handler(MessageHandler(Filters.document, handle_document))
    dispatcher.add_handler(CallbackQueryHandler(handle_callback_query))
    
    logging.info("🚀 批量上传机器人启动成功")
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()