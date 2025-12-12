#!/usr/bin/env python3
"""
初始化 MongoDB 数据库脚本
Initialize MongoDB Database Script
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

# 加载环境变量
load_dotenv()

def init_database():
    """初始化 MongoDB 数据库"""
    print("🔧 初始化 MongoDB 数据库...")
    
    # 获取配置
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    database_name = os.getenv('MONGODB_DATABASE', 'telegram_bot')
    
    print(f"📊 连接到: {mongodb_uri}")
    print(f"📦 数据库: {database_name}")
    
    try:
        # 连接到 MongoDB
        client = MongoClient(mongodb_uri)
        db = client[database_name]
        
        # 测试连接
        client.admin.command('ping')
        print("✅ 成功连接到 MongoDB!")
        
        # 创建集合（如果不存在）
        collections = ['accounts', 'tasks', 'targets', 'message_logs']
        
        for collection_name in collections:
            if collection_name not in db.list_collection_names():
                db.create_collection(collection_name)
                print(f"✅ 创建集合: {collection_name}")
            else:
                print(f"ℹ️  集合已存在: {collection_name}")
        
        # 创建索引
        print("\n🔧 创建索引...")
        
        # accounts 索引
        db.accounts.create_index('phone', unique=True)
        db.accounts.create_index('session_name', unique=True)
        db.accounts.create_index('status')
        print("✅ 创建 accounts 索引")
        
        # tasks 索引
        db.tasks.create_index('status')
        db.tasks.create_index('account_id')
        print("✅ 创建 tasks 索引")
        
        # targets 索引
        db.targets.create_index('task_id')
        db.targets.create_index('is_sent')
        db.targets.create_index([('task_id', 1), ('is_sent', 1)])
        print("✅ 创建 targets 索引")
        
        # message_logs 索引
        db.message_logs.create_index('task_id')
        db.message_logs.create_index('account_id')
        db.message_logs.create_index('sent_at')
        print("✅ 创建 message_logs 索引")
        
        print("\n✅ 数据库初始化完成！")
        print(f"📊 MongoDB URI: {mongodb_uri}")
        print(f"📦 数据库名称: {database_name}")
        print(f"📋 集合数量: {len(collections)}")
        
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return False
    
    return True


if __name__ == '__main__':
    success = init_database()
    exit(0 if success else 1)
