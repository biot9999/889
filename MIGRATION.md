# 数据库迁移指南 / Database Migration Guide

## 从 SQLite 迁移到 MongoDB / Migrating from SQLite to MongoDB

### 为什么迁移到 MongoDB？/ Why Migrate to MongoDB?

MongoDB 提供以下优势：
MongoDB provides these advantages:

1. **更好的性能** / Better Performance - 大数据量下表现更好
2. **更灵活的数据模型** / Flexible Data Model - 无需预定义严格的表结构
3. **更容易扩展** / Easy Scalability - 支持水平扩展和分片
4. **更简单的部署** / Simpler Deployment - 无需复杂的迁移脚本

## 迁移步骤 / Migration Steps

### 步骤 1：安装 MongoDB / Step 1: Install MongoDB

**Ubuntu/Debian:**
```bash
wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

**CentOS/RHEL:**
```bash
sudo tee /etc/yum.repos.d/mongodb-org-6.0.repo << EOF
[mongodb-org-6.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/\$releasever/mongodb-org/6.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-6.0.asc
EOF
sudo yum install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

**Docker:**
```bash
docker run -d --name mongodb -p 27017:27017 mongo:6.0
```

### 步骤 2：更新配置文件 / Step 2: Update Configuration

编辑 `.env` 文件，替换数据库配置：
Edit `.env` file and replace database configuration:

**旧配置 / Old Configuration:**
```env
DATABASE_URL=sqlite:///telegram_bot.db
```

**新配置 / New Configuration:**
```env
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=telegram_bot
```

### 步骤 3：更新 Python 依赖 / Step 3: Update Python Dependencies

```bash
# 确保使用最新的 requirements.txt
# Ensure using latest requirements.txt
pip install -r requirements.txt
```

### 步骤 4：初始化 MongoDB 数据库 / Step 4: Initialize MongoDB Database

```bash
# 初始化 MongoDB 集合和索引
# Initialize MongoDB collections and indexes
python3 init_db.py
```

### 步骤 5：迁移现有数据（可选）/ Step 5: Migrate Existing Data (Optional)

如果你有现有的 SQLite 数据需要迁移：
If you have existing SQLite data to migrate:

```bash
# 运行迁移脚本
# Run migration script
python3 migrate_db.py
```

该脚本将：
This script will:
- 从 SQLite 读取所有数据
- 转换数据格式
- 导入到 MongoDB
- 保留所有账户、任务、目标和日志

### 步骤 6：验证迁移 / Step 6: Verify Migration

```bash
# 启动机器人
# Start the bot
python3 bot.py
```

检查：
Check:
1. ✅ 机器人启动无错误 / Bot starts without errors
2. ✅ 可以查看账户列表 / Can view account list
3. ✅ 可以查看任务列表 / Can view task list
4. ✅ 统计数据正确 / Statistics are correct

### 步骤 7：备份 SQLite 数据库（可选）/ Step 7: Backup SQLite Database (Optional)

迁移成功后，建议备份原 SQLite 数据库：
After successful migration, backup the original SQLite database:

```bash
# 移动到备份目录
# Move to backup directory
mkdir -p backups
mv telegram_bot.db backups/telegram_bot.db.$(date +%Y%m%d)
```

## 验证 MongoDB 连接 / Verify MongoDB Connection

使用 MongoDB Shell 验证数据：
Verify data using MongoDB Shell:

```bash
# 连接到 MongoDB
# Connect to MongoDB
mongosh

# 切换到数据库
# Switch to database
use telegram_bot

# 查看集合
# List collections
show collections

# 统计文档数量
# Count documents
db.accounts.countDocuments()
db.tasks.countDocuments()
db.targets.countDocuments()
db.message_logs.countDocuments()

# 查看示例文档
# View sample documents
db.accounts.findOne()
db.tasks.findOne()
```

## 故障排除 / Troubleshooting

### 问题 1: 无法连接到 MongoDB / Cannot Connect to MongoDB

```bash
# 检查 MongoDB 服务状态
# Check MongoDB service status
sudo systemctl status mongod

# 检查 MongoDB 日志
# Check MongoDB logs
sudo tail -f /var/log/mongodb/mongod.log
```

### 问题 2: 迁移脚本失败 / Migration Script Fails

```bash
# 检查 SQLite 文件是否存在
# Check if SQLite file exists
ls -lh telegram_bot.db

# 手动测试 SQLite 连接
# Manually test SQLite connection
sqlite3 telegram_bot.db "SELECT COUNT(*) FROM accounts;"
```

### 问题 3: 数据不完整 / Data Incomplete

```bash
# 重新运行迁移脚本（会跳过已存在的数据）
# Re-run migration script (will skip existing data)
python3 migrate_db.py

# 或清空 MongoDB 重新迁移
# Or clear MongoDB and re-migrate
mongosh
use telegram_bot
db.dropDatabase()
exit
python3 init_db.py
python3 migrate_db.py
```

## 性能优化建议 / Performance Optimization Tips

1. **创建索引** / Create Indexes
   ```javascript
   // 在 MongoDB Shell 中
   use telegram_bot
   db.accounts.createIndex({"phone": 1})
   db.tasks.createIndex({"status": 1})
   db.targets.createIndex({"task_id": 1, "is_sent": 1})
   ```

2. **定期备份** / Regular Backups
   ```bash
   # 导出数据库
   mongodump --db telegram_bot --out /backup/$(date +%Y%m%d)
   
   # 恢复数据库
   mongorestore --db telegram_bot /backup/20231201/telegram_bot
   ```

3. **监控性能** / Monitor Performance
   ```javascript
   // 在 MongoDB Shell 中查看慢查询
   db.setProfilingLevel(1, 100)
   db.system.profile.find().pretty()
   ```

## 新功能 / New Features

迁移到 MongoDB 后，你的机器人将享有：
After migrating to MongoDB, your bot will benefit from:

1. **更快的查询速度** / Faster Query Speed
2. **更好的并发处理** / Better Concurrency
3. **更灵活的数据结构** / More Flexible Data Structure
4. **更简单的扩展** / Easier Scaling

## 需要帮助？/ Need Help?

如果遇到问题，请提供以下信息：
If you encounter issues, please provide:

1. 错误消息完整内容 / Full error message
2. Python 版本 / Python version: `python3 --version`
3. MongoDB 版本 / MongoDB version: `mongod --version`
4. 运行的命令 / Command you ran
5. MongoDB 日志 / MongoDB logs
