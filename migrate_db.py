#!/usr/bin/env python3
"""
MongoDB 数据库迁移脚本 - 从 SQLite 迁移到 MongoDB
Migration script from SQLite to MongoDB

注意：本脚本用于将数据从旧的 SQLite 数据库迁移到 MongoDB
Note: This script is used to migrate data from old SQLite database to MongoDB

使用方法：
1. 确保已安装 MongoDB 并正在运行
2. 配置 .env 文件中的 MONGODB_URI 和 MONGODB_DATABASE
3. 运行此脚本

Usage:
1. Ensure MongoDB is installed and running
2. Configure MONGODB_URI and MONGODB_DATABASE in .env file
3. Run this script
"""
import os
import sqlite3
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime

# 加载环境变量
load_dotenv()

def migrate_sqlite_to_mongodb():
    """从 SQLite 迁移数据到 MongoDB"""
    print("🔧 开始从 SQLite 迁移到 MongoDB...")
    
    # SQLite 数据库路径
    sqlite_db = os.getenv('DATABASE_URL', 'sqlite:///telegram_bot.db').replace('sqlite:///', '')
    
    if not os.path.exists(sqlite_db):
        print("❌ SQLite 数据库文件不存在")
        print("💡 如果您是新安装，请直接使用 init_db.py 初始化 MongoDB")
        return False
    
    # MongoDB 配置
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    database_name = os.getenv('MONGODB_DATABASE', 'telegram_bot')
    
    print(f"📊 从 SQLite 迁移: {sqlite_db}")
    print(f"📊 到 MongoDB: {mongodb_uri}/{database_name}")
    
    try:
        # 连接 SQLite
        sqlite_conn = sqlite3.connect(sqlite_db)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        
        # 连接 MongoDB
        mongo_client = MongoClient(mongodb_uri)
        mongo_db = mongo_client[database_name]
        
        # 迁移 accounts
        print("\n🔄 迁移 accounts...")
        sqlite_cursor.execute("SELECT * FROM accounts")
        accounts = sqlite_cursor.fetchall()
        if accounts:
            accounts_data = []
            for row in accounts:
                accounts_data.append({
                    'phone': row['phone'],
                    'session_name': row['session_name'],
                    'status': row['status'],
                    'api_id': row['api_id'],
                    'api_hash': row['api_hash'],
                    'messages_sent_today': row['messages_sent_today'],
                    'total_messages_sent': row['total_messages_sent'],
                    'last_used': datetime.fromisoformat(row['last_used']) if row['last_used'] else None,
                    'daily_limit': row['daily_limit'],
                    'created_at': datetime.fromisoformat(row['created_at']) if row['created_at'] else datetime.utcnow(),
                    'updated_at': datetime.fromisoformat(row['updated_at']) if row['updated_at'] else datetime.utcnow()
                })
            mongo_db.accounts.insert_many(accounts_data)
            print(f"✅ 迁移 {len(accounts)} 个账户")
        
        # 迁移 tasks
        print("\n🔄 迁移 tasks...")
        sqlite_cursor.execute("SELECT * FROM tasks")
        tasks = sqlite_cursor.fetchall()
        if tasks:
            tasks_data = []
            for row in tasks:
                tasks_data.append({
                    'name': row['name'],
                    'status': row['status'],
                    'message_text': row['message_text'],
                    'message_format': row['message_format'],
                    'media_type': row['media_type'],
                    'media_path': row['media_path'],
                    'send_method': row.get('send_method', 'direct'),
                    'postbot_code': row.get('postbot_code'),
                    'channel_link': row.get('channel_link'),
                    'min_interval': row['min_interval'],
                    'max_interval': row['max_interval'],
                    'account_id': str(row['account_id']) if row['account_id'] else None,
                    'total_targets': row['total_targets'],
                    'sent_count': row['sent_count'],
                    'failed_count': row['failed_count'],
                    'created_at': datetime.fromisoformat(row['created_at']) if row['created_at'] else datetime.utcnow(),
                    'started_at': datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                    'completed_at': datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    'updated_at': datetime.fromisoformat(row['updated_at']) if row['updated_at'] else datetime.utcnow()
                })
            mongo_db.tasks.insert_many(tasks_data)
            print(f"✅ 迁移 {len(tasks)} 个任务")
        
        # 迁移 targets  
        print("\n🔄 迁移 targets...")
        sqlite_cursor.execute("SELECT * FROM targets")
        targets = sqlite_cursor.fetchall()
        if targets:
            targets_data = []
            for row in targets:
                targets_data.append({
                    'task_id': str(row['task_id']),
                    'username': row['username'],
                    'user_id': row['user_id'],
                    'first_name': row['first_name'],
                    'last_name': row['last_name'],
                    'is_sent': bool(row['is_sent']),
                    'is_valid': bool(row['is_valid']),
                    'error_message': row['error_message'],
                    'created_at': datetime.fromisoformat(row['created_at']) if row['created_at'] else datetime.utcnow(),
                    'sent_at': datetime.fromisoformat(row['sent_at']) if row['sent_at'] else None
                })
            mongo_db.targets.insert_many(targets_data)
            print(f"✅ 迁移 {len(targets)} 个目标")
        
        # 迁移 message_logs
        print("\n🔄 迁移 message_logs...")
        sqlite_cursor.execute("SELECT * FROM message_logs")
        logs = sqlite_cursor.fetchall()
        if logs:
            logs_data = []
            for row in logs:
                logs_data.append({
                    'task_id': str(row['task_id']),
                    'account_id': str(row['account_id']),
                    'target_id': str(row['target_id']),
                    'message_text': row['message_text'],
                    'success': bool(row['success']),
                    'error_message': row['error_message'],
                    'sent_at': datetime.fromisoformat(row['sent_at']) if row['sent_at'] else datetime.utcnow()
                })
            mongo_db.message_logs.insert_many(logs_data)
            print(f"✅ 迁移 {len(logs)} 条消息日志")
        
        sqlite_conn.close()
        
        print("\n✅ 数据迁移完成！")
        print("💡 建议：验证数据后，可以备份并删除旧的 SQLite 数据库文件")
        
        return True
        
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = migrate_sqlite_to_mongodb()
    exit(0 if success else 1)

