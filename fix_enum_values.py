#!/usr/bin/env python3
"""
修复数据库中的枚举值问题
Fix enum value issues in the database
"""
import os
import sqlite3
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def fix_enum_values():
    """修复数据库中的枚举值，确保它们与代码中的枚举定义匹配"""
    print("🔧 开始修复枚举值...")
    
    # 获取数据库路径
    database_url = os.getenv('DATABASE_URL', 'sqlite:///telegram_bot.db')
    db_path = database_url.replace('sqlite:///', '')
    
    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    print(f"📊 数据库位置: {db_path}")
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查 tasks 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            print("❌ tasks 表不存在")
            return
        
        # 检查是否有 send_method 列
        cursor.execute("PRAGMA table_info(tasks)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        if 'send_method' not in columns:
            print("⚠️  send_method 列不存在，请先运行 migrate_db.py")
            return
        
        print("\n📋 检查任务表中的数据...")
        
        # 查看当前的 send_method 值
        cursor.execute("SELECT id, name, send_method FROM tasks")
        tasks = cursor.fetchall()
        
        if not tasks:
            print("ℹ️  没有现有任务，无需修复")
            return
        
        print(f"找到 {len(tasks)} 个任务")
        
        # 统计需要修复的任务
        null_count = 0
        invalid_count = 0
        valid_enums = ['direct', 'postbot', 'channel_forward', 'channel_forward_hidden']
        
        for task_id, name, send_method in tasks:
            if send_method is None:
                null_count += 1
            elif send_method not in valid_enums:
                invalid_count += 1
                print(f"⚠️  任务 #{task_id} ({name}) 有无效的 send_method: {send_method}")
        
        if null_count > 0:
            print(f"\n🔧 修复 {null_count} 个 NULL 值...")
            cursor.execute("UPDATE tasks SET send_method = 'direct' WHERE send_method IS NULL")
            print(f"✅ 已为 {null_count} 个任务设置默认值 'direct'")
        
        if invalid_count > 0:
            print(f"\n🔧 修复 {invalid_count} 个无效值...")
            # 尝试修复常见的无效值
            cursor.execute("UPDATE tasks SET send_method = 'direct' WHERE send_method NOT IN ('direct', 'postbot', 'channel_forward', 'channel_forward_hidden')")
            print(f"✅ 已修复 {invalid_count} 个无效值")
        
        # 提交更改
        conn.commit()
        
        # 验证修复结果
        cursor.execute("SELECT DISTINCT send_method FROM tasks")
        distinct_values = [row[0] for row in cursor.fetchall()]
        print(f"\n📋 修复后的 send_method 值: {distinct_values}")
        
        # 检查是否还有无效值
        invalid_values = [v for v in distinct_values if v not in valid_enums]
        if invalid_values:
            print(f"⚠️  仍有无效值: {invalid_values}")
        else:
            print("✅ 所有 send_method 值都有效！")
        
        print("\n✅ 枚举值修复完成！")
        
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    fix_enum_values()
