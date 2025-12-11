# 数据库迁移指南 / Database Migration Guide

## 问题 / Problem

如果你在使用新版本时遇到以下错误：
If you encounter this error when using the new version:

```
sqlite3.OperationalError: table tasks has no column named send_method
```

这是因为你的数据库是旧版本创建的，缺少新增的列。
This is because your database was created with an old version and is missing new columns.

## 解决方案 / Solution

### 方案 1：运行迁移脚本（推荐）/ Run Migration Script (Recommended)

这个方法会保留你现有的数据。
This method preserves your existing data.

```bash
python3 migrate_db.py
```

迁移脚本会自动添加以下新列：
The migration script will automatically add these new columns:
- `send_method` - 发送方式
- `postbot_code` - Post代码
- `channel_link` - 频道链接

### 方案 2：重新初始化数据库 / Reinitialize Database

**⚠️ 警告：这会删除所有现有数据！**
**⚠️ Warning: This will delete all existing data!**

```bash
# 1. 备份旧数据库（如果需要）
# Backup old database (if needed)
cp telegram_bot.db telegram_bot.db.backup

# 2. 删除旧数据库
# Delete old database
rm telegram_bot.db

# 3. 重新初始化
# Reinitialize
python3 init_db.py
```

## 验证 / Verification

运行迁移后，启动机器人应该不再有错误：
After migration, starting the bot should no longer show errors:

```bash
python3 bot.py
```

## 新功能 / New Features

迁移后，你的机器人将支持以下新功能：
After migration, your bot will support these new features:

1. **发送方式选择** / Send Method Selection
   - 📤 直接发送 / Direct Send
   - 🤖 Post代码 / Postbot Code
   - 📢 频道转发 / Channel Forward
   - 🔒 隐藏转发来源 / Hidden Source Forward

2. **预览功能** / Preview Feature
   - 在发送前预览配置 / Preview configuration before sending
   - 可以返回修改 / Can go back to modify

3. **去重统计** / Deduplication Stats
   - 显示收到和去重的用户数 / Shows received and deduplicated user counts

## 需要帮助？/ Need Help?

如果遇到问题，请提供以下信息：
If you encounter issues, please provide:

1. 错误消息完整内容 / Full error message
2. Python 版本 / Python version: `python3 --version`
3. 数据库文件位置 / Database file location
4. 运行的命令 / Command you ran
