# 快速启动指南

本指南将帮助您在 5 分钟内启动 Telegram 私信机器人。

## 📋 前置要求

1. Python 3.8 或更高版本
2. Telegram 账号
3. 基本的命令行操作知识

## 🚀 快速启动（5 步骤）

### 步骤 1: 安装依赖

```bash
pip install python-telegram-bot telethon sqlalchemy cryptography python-dotenv
```

### 步骤 2: 创建机器人

1. 在 Telegram 搜索 `@BotFather`
2. 发送 `/newbot`
3. 按提示设置机器人名称和用户名
4. **保存** 获得的 Token

### 步骤 3: 获取 API 凭据

1. 访问 https://my.telegram.org
2. 登录您的 Telegram 账号
3. 点击 "API development tools"
4. 创建应用
5. **保存** API ID 和 API Hash

### 步骤 4: 配置环境变量

创建 `.env` 文件：

```bash
cp .env.example .env
nano .env  # 或使用您喜欢的编辑器
```

填入以下信息：

```env
BOT_TOKEN=你的机器人Token
API_ID=你的API_ID
API_HASH=你的API_Hash
```

生成加密密钥（可选，如不填写会自动生成）：

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将生成的密钥填入 `ENCRYPTION_KEY`。

### 步骤 5: 启动机器人

```bash
python3 sxbot.py
```

看到以下输出表示启动成功：

```
机器人已启动，按 Ctrl+C 停止
```

## 🎉 开始使用

1. 在 Telegram 中搜索您的机器人
2. 点击 "Start" 或发送 `/start`
3. 使用内联按钮开始操作！

## 📖 主要功能

### 添加账户

1. 点击 "📱 账户管理"
2. 点击 "➕ 添加账户"
3. 选择 "🔑 Session String"
4. 粘贴您的 Session String

**如何获取 Session String？**

运行以下 Python 代码：

```python
from telethon import TelegramClient
from telethon.sessions import StringSession

# 填入您在步骤3获取的信息
API_ID = 你的API_ID
API_HASH = '你的API_Hash'

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("你的 Session String:")
    print(client.session.save())
```

### 创建任务

1. 点击 "📝 任务管理"
2. 点击 "➕ 创建新任务"
3. 选择消息类型（如：📝 纯文本）
4. 选择格式化方式（如：Markdown）
5. 输入消息模板：

```
你好 **{name}**！

这是一条测试消息。
```

6. 输入目标用户列表：

```
@username1
@username2
```

7. 任务创建完成！

### 执行任务

1. 点击 "📝 任务管理" → "📋 任务列表"
2. 选择任务
3. 点击 "▶️ 开始执行"
4. 任务在后台运行，可随时查看进度

## 🔧 常见问题

### Q: 机器人无法启动？

A: 检查：
- Python 版本是否 ≥ 3.8
- 依赖是否全部安装
- `.env` 配置是否正确
- BOT_TOKEN 是否有效

### Q: Session String 无效？

A: 确保：
- API_ID 和 API_HASH 正确
- Session String 完整复制
- 账户没有被 Telegram 限制

### Q: 消息发送失败？

A: 可能原因：
- 账户被限制（检查账户状态）
- 目标用户设置了隐私保护
- 发送频率过快（调整延迟）

### Q: 如何查看日志？

A: 日志文件在 `bot.log`

```bash
tail -f bot.log
```

## 📞 获取帮助

- 查看 [README.md](README.md) 了解完整功能
- 查看 [BAOTA_DEPLOY.md](BAOTA_DEPLOY.md) 了解宝塔部署
- 通过 GitHub Issues 报告问题

## ⚠️ 重要提示

1. **遵守法律法规**：请勿发送垃圾信息或骚扰他人
2. **保护隐私**：不要分享您的 Token、Session String 等敏感信息
3. **合理使用**：设置适当的发送延迟和限制，避免账户被封
4. **测试先行**：先用少量目标测试，确认无误后再大规模使用

---

**祝您使用愉快！** 🎉
