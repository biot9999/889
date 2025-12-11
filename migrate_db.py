#!/usr/bin/env python3
"""
数据库迁移脚本 - 添加新列到现有数据库
Migration script to add new columns to existing database
"""
import os
import sqlite3
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def migrate_database():
    """迁移数据库，添加缺失的列"""
    print("🔧 开始数据库迁移...")
    
    # 获取数据库路径
    database_url = os.getenv('DATABASE_URL', 'sqlite:///telegram_bot.db')
    db_path = database_url.replace('sqlite:///', '')
    
    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        print("💡 请先运行 python3 init_db.py 初始化数据库")
        return
    
    print(f"📊 数据库位置: {db_path}")
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查 tasks 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            print("❌ tasks 表不存在，请先运行 init_db.py")
            return
        
        # 获取现有列
        cursor.execute("PRAGMA table_info(tasks)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        print(f"📋 现有列: {existing_columns}")
        
        # 需要添加的列
        new_columns = [
            ("send_method", "VARCHAR(50) DEFAULT 'direct'"),
            ("postbot_code", "TEXT"),
            ("channel_link", "VARCHAR(500)")
        ]
        
        # 添加缺失的列
        added_count = 0
        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}")
                    print(f"✅ 已添加列: {col_name}")
                    added_count += 1
                except sqlite3.OperationalError as e:
                    print(f"⚠️  添加列 {col_name} 时出错: {e}")
            else:
                print(f"ℹ️  列已存在: {col_name}")
        
        # 提交更改
        conn.commit()
        
        if added_count > 0:
            print(f"\n✅ 迁移完成！成功添加 {added_count} 个新列")
        else:
            print("\n✅ 数据库已是最新版本，无需迁移")
        
        # 验证
        cursor.execute("PRAGMA table_info(tasks)")
        all_columns = [row[1] for row in cursor.fetchall()]
        print(f"\n📋 迁移后的列: {', '.join(all_columns)}")
        
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    migrate_database()
