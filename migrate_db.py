#!/usr/bin/env python3
"""
MongoDB 数据库 - 无需迁移
MongoDB Database - No Migration Needed

说明 / Note:
本项目已完全切换到 MongoDB，不再使用 SQLite。
This project has completely switched to MongoDB and no longer uses SQLite.

如果您是新用户：
If you are a new user:
1. 安装 MongoDB / Install MongoDB
2. 配置 .env 文件 / Configure .env file
3. 运行 python3 init_db.py / Run python3 init_db.py
4. 启动机器人 / Start the bot

如果您之前使用过 SQLite 版本：
If you previously used the SQLite version:
- 不支持自动迁移 / Automatic migration is not supported
- 建议重新开始使用 MongoDB / It is recommended to start fresh with MongoDB
- 账户信息需要重新添加 / Account information needs to be re-added
"""

print("ℹ️  本项目使用 MongoDB 数据库")
print("ℹ️  This project uses MongoDB database")
print()
print("📝 请运行以下命令初始化数据库：")
print("📝 Please run the following command to initialize the database:")
print("   python3 init_db.py")
print()
print("💡 不支持从 SQLite 自动迁移数据")
print("💡 Automatic migration from SQLite is not supported")


