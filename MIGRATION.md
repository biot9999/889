# MongoDB 数据库使用指南 / MongoDB Database Usage Guide

## MongoDB 数据库 / MongoDB Database

本项目已完全切换到 MongoDB，不再使用 SQLite。
This project has completely switched to MongoDB and no longer uses SQLite.

### 为什么使用 MongoDB？/ Why Use MongoDB?

MongoDB 提供以下优势：
MongoDB provides these advantages:

1. **更好的性能** / Better Performance - 大数据量下表现更好
2. **更灵活的数据模型** / Flexible Data Model - 无需预定义严格的表结构
3. **更容易扩展** / Easy Scalability - 支持水平扩展和分片
4. **更简单的部署** / Simpler Deployment - 无需复杂的迁移脚本

## 安装步骤 / Installation Steps

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

编辑 `.env` 文件：
Edit `.env` file:

```env
# MongoDB 数据库配置
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=telegram_bot
```

### 步骤 3：安装 Python 依赖 / Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 步骤 4：初始化 MongoDB 数据库 / Step 4: Initialize MongoDB Database

```bash
# 初始化 MongoDB 集合和索引
# Initialize MongoDB collections and indexes
python3 init_db.py
```

### 步骤 5：启动机器人 / Step 5: Start the Bot

```bash
# 启动机器人
# Start the bot
python3 bot.py
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

### 问题 2: 初始化失败 / Initialization Failed

```bash
# 确保 MongoDB 正在运行
# Ensure MongoDB is running
sudo systemctl restart mongod

# 检查配置
# Check configuration
cat .env | grep MONGODB
```

### 问题 3: 权限问题 / Permission Issues

```bash
# MongoDB 默认不需要认证
# MongoDB does not require authentication by default

# 如果启用了认证，在 .env 中配置：
# If authentication is enabled, configure in .env:
MONGODB_URI=mongodb://username:password@localhost:27017/
```

## 性能优化建议 / Performance Optimization Tips

1. **索引已自动创建** / Indexes Are Automatically Created
   - init_db.py 已经创建了所有必要的索引
   - init_db.py has created all necessary indexes

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

## 数据管理 / Data Management

### 清空数据库 / Clear Database

如果需要重新开始：
If you need to start fresh:

```bash
mongosh
use telegram_bot
db.dropDatabase()
exit
python3 init_db.py
```

### 查看数据 / View Data

```bash
mongosh
use telegram_bot

# 查看账户
db.accounts.find().pretty()

# 查看任务
db.tasks.find().pretty()
```

## 从旧版本升级 / Upgrading from Old Version

如果您之前使用 SQLite 版本：
If you previously used the SQLite version:

- ⚠️ **不支持自动数据迁移** / Automatic data migration is not supported
- 💡 建议：重新开始使用 MongoDB / Recommended: Start fresh with MongoDB
- 📝 账户信息需要重新添加 / Account information needs to be re-added
- 🔄 任务需要重新创建 / Tasks need to be recreated

## 需要帮助？/ Need Help?

如果遇到问题，请提供以下信息：
If you encounter issues, please provide:

1. 错误消息完整内容 / Full error message
2. Python 版本 / Python version: `python3 --version`
3. MongoDB 版本 / MongoDB version: `mongod --version`
4. 运行的命令 / Command you ran
5. MongoDB 日志 / MongoDB logs
