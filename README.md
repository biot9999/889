# Telegram 私信机器人管理系统

一个功能强大的 Telegram 机器人管理系统，用于管理多个 Telegram 账户并执行批量私信任务。采用**内联按钮**交互方式，无需记忆命令。**参考 TeleRaptor 核心特点**开发，支持富媒体、消息个性化和高级格式化。

## ✨ 功能特性

### 📱 账户管理
- ✅ 支持通过 Session String 添加账户
- ✅ 支持通过手机号+验证码登录添加账户（开发中）
- ✅ 账户状态监控（active, banned, limited）
- ✅ 账户信息加密存储
- ✅ 自动检测账户可用性
- ✅ 多账户并发支持

### 📝 任务管理（TeleRaptor 风格）
- ✅ **富媒体支持**：文本、图片、视频、语音、文档
- ✅ **消息个性化**：支持变量替换（{name}, {first_name}, {last_name}, {full_name}, {username}）
- ✅ **高级格式化**：Markdown、HTML、纯文本格式
- ✅ **目标列表上传**：支持用户名和ID混合输入
- ✅ **智能账户分配**：自动轮询使用活跃账户
- ✅ **实时任务状态监控**
- ✅ **任务开始/停止控制**

### 🎨 消息格式化（参考 TeleRaptor）
- ✅ **Markdown 支持**：`**粗体**`、`*斜体*`、`[链接](URL)`、`` `代码` ``
- ✅ **HTML 支持**：`<b>粗体</b>`、`<i>斜体</i>`、`<a href='URL'>链接</a>`、`<code>代码</code>`
- ✅ **链接隐藏**：将URL隐藏在文字下方
- ✅ **富文本组合**：支持多种格式组合使用

### 💬 消息个性化（参考 TeleRaptor）
每条消息都可以根据目标用户自动个性化：
- `{name}` - 自动替换为用户名或名字
- `{first_name}` - 用户的名字
- `{last_name}` - 用户的姓氏
- `{full_name}` - 用户的全名
- `{username}` - 用户的 @用户名

**示例**：
```
你好 {name}！

这是一条测试消息，**{full_name}**！

访问我们的网站：[点击这里](https://example.com)
```

### 🛡️ 安全特性
- ✅ Session String 使用 Fernet 加密存储
- ✅ 支持用户白名单机制
- ✅ API 密钥环境变量配置
- ✅ 敏感信息不记录到日志
- ✅ 账户权限验证

### 🚀 防封策略
- ✅ 消息发送间隔随机化（默认 30-120 秒）
- ✅ 每账户每天发送限制（默认 50 条）
- ✅ 账户状态实时监控
- ✅ 自动暂停受限账户
- ✅ 智能错误处理和重试

### 🎨 用户体验
- ✅ **内联按钮交互**，无需记忆命令
- ✅ 友好的按钮界面
- ✅ 分步骤引导配置
- ✅ 实时显示任务进度
- ✅ 清晰的错误提示和帮助信息
- ✅ 媒体类型可视化选择
- ✅ 格式化模式可视化选择

## 📦 安装指南

### 1. 环境要求
- Python 3.8+
- pip

### 2. 克隆项目
```bash
git clone https://github.com/yourusername/telegram-bot.git
cd telegram-bot
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 配置环境变量
```bash
cp .env.example .env
```

编辑 `.env` 文件，填入以下配置：

```env
# 机器人配置
BOT_TOKEN=your_bot_token_here  # 从 @BotFather 获取
API_ID=your_api_id  # 从 https://my.telegram.org 获取
API_HASH=your_api_hash  # 从 https://my.telegram.org 获取

# 数据库配置（默认使用 SQLite）
DATABASE_URL=sqlite:///telegram_bot.db

# 安全配置
ENCRYPTION_KEY=your_encryption_key_here  # 32字节密钥
ALLOWED_USERS=  # 留空允许所有用户，或填入用户ID，如: 123456,789012

# 发送限制配置
MAX_MESSAGES_PER_ACCOUNT_PER_DAY=50
MIN_DELAY_SECONDS=30
MAX_DELAY_SECONDS=120
```

### 5. 运行机器人
```bash
python sxbot.py
```

## 🎯 使用教程

### 获取机器人 Token
1. 在 Telegram 中搜索 `@BotFather`
2. 发送 `/newbot` 命令
3. 按提示设置机器人名称和用户名
4. 复制获得的 Token 到 `.env` 文件

### 获取 API ID 和 API Hash
1. 访问 https://my.telegram.org
2. 登录您的 Telegram 账号
3. 点击 "API development tools"
4. 创建应用并获取 API ID 和 API Hash

### 生成加密密钥
在 Python 中运行：
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### 使用机器人

#### 1. 启动机器人
在 Telegram 中搜索您的机器人，点击 "Start" 或发送 `/start`

#### 2. 主菜单
机器人会显示主菜单，包含以下选项：
- 📱 **账户管理** - 添加和管理 Telegram 账户
- 📝 **任务管理** - 创建和管理私信任务
- ⚙️ **全局设置** - 查看系统配置
- ❓ **帮助文档** - 查看使用说明

#### 3. 添加账户
1. 点击 "📱 账户管理"
2. 点击 "➕ 添加账户"
3. 选择添加方式：
   - **🔑 Session String**: 直接粘贴从 Telethon 导出的 Session String
   - **📞 手机号登录**: 输入手机号并接收验证码（开发中）

#### 4. 创建任务
1. 点击 "📝 任务管理"
2. 点击 "➕ 创建新任务"
3. 按步骤操作：
   - **步骤 1**: 选择消息类型（文本/图片/视频/语音/文档）
   - **步骤 2**: 选择文本格式化方式（Markdown/HTML/无格式）
   - **步骤 3**: 输入消息模板（支持个性化变量和格式化）
   - **步骤 4**: 如需要，上传媒体文件
   - **步骤 5**: 输入目标用户列表（每行一个用户名或ID）
   - 系统自动选择活跃账户并创建任务

#### 5. 消息模板示例

**纯文本（无格式）：**
```
你好 {name}，欢迎！
```

**Markdown 格式：**
```
你好 **{name}**！

这是一条 *重要* 消息。

访问：[我们的网站](https://example.com)

代码：`print("Hello")`
```

**HTML 格式：**
```
你好 <b>{name}</b>！

这是一条 <i>重要</i> 消息。

访问：<a href="https://example.com">我们的网站</a>

代码：<code>print("Hello")</code>
```

**个性化变量：**
```
尊敬的 {full_name}，

您好！我是 @username。

{first_name}，感谢您的关注！
```

#### 6. 执行任务
1. 在 "📝 任务管理" 中点击 "📋 任务列表"
2. 选择要执行的任务
3. 查看任务详情（类型、目标数量、格式化方式等）
4. 点击 "▶️ 开始执行"
5. 任务将在后台运行，可随时查看进度或停止

## 🎯 功能对比

### 与 TeleRaptor 的相似功能

| 功能 | 本项目 | TeleRaptor |
|------|--------|------------|
| 富媒体支持 | ✅ 文本/图片/视频/语音/文档 | ✅ |
| 消息个性化 | ✅ 5种变量 | ✅ |
| 格式化支持 | ✅ Markdown/HTML | ✅ |
| 多账户管理 | ✅ | ✅ |
| 智能延迟 | ✅ 随机30-120秒 | ✅ |
| 账户状态监控 | ✅ | ✅ |
| 内联按钮界面 | ✅ | ❌ |
| 免费开源 | ✅ | ❌ |
| 跨平台 | ✅ Linux/Windows/Mac | ❌ 仅Windows |
| 宝塔部署 | ✅ | ❌ |

## 🗂️ 数据库结构

系统使用 SQLite 数据库，包含以下表：

### users - 用户表
- `id`: 主键
- `telegram_id`: Telegram 用户 ID（唯一）
- `username`: 用户名
- `created_at`: 创建时间

### accounts - 账户表
- `id`: 主键
- `user_id`: 用户ID（外键）
- `session_string`: Session String（加密）
- `phone_number`: 手机号
- `status`: 状态（active/banned/limited）
- `messages_sent_today`: 今日发送计数
- `last_used_at`: 最后使用时间
- `created_at`: 创建时间

### tasks - 任务表
- `id`: 主键
- `user_id`: 用户ID（外键）
- `message_template`: 消息模板
- `target_list`: 目标列表（JSON）
- `account_ids`: 账户ID列表（JSON）
- `status`: 状态（pending/running/completed/failed/stopped）
- `config`: 配置（JSON）
- `progress`: 进度（JSON）
- `media_type`: 媒体类型（text/photo/video/voice/document）
- `media_url`: 媒体文件URL或路径
- `parse_mode`: 解析模式（Markdown/HTML/None）
- `created_at`: 创建时间
- `started_at`: 开始时间
- `completed_at`: 完成时间

### send_logs - 发送日志表
- `id`: 主键
- `task_id`: 任务ID（外键）
- `account_id`: 账户ID（外键）
- `target_user`: 目标用户
- `success`: 是否成功
- `error_message`: 错误信息
- `sent_at`: 发送时间

## 🔒 安全建议

1. **保护配置文件**
   - 不要将 `.env` 文件提交到版本控制
   - 定期更换加密密钥
   - 使用强密码和安全的 Token

2. **设置用户白名单**
   - 在 `.env` 中配置 `ALLOWED_USERS`
   - 只允许信任的用户使用机器人

3. **合理设置发送限制**
   - 不要设置过高的发送频率
   - 建议每条消息间隔 30 秒以上
   - 每账户每天不超过 50 条消息

4. **监控账户状态**
   - 定期检查账户状态
   - 及时处理被限制的账户
   - 避免使用同一账户频繁发送

## ⚠️ 免责声明

本项目仅供学习和研究使用。使用者应遵守 Telegram 服务条款和当地法律法规。

**禁止用于以下用途：**
- 发送垃圾信息
- 骚扰他人
- 传播违法内容
- 其他违反 Telegram 服务条款的行为

使用本项目造成的任何后果由使用者自行承担，开发者不承担任何责任。

## 📝 常见问题

### Q: 如何获取 Session String？
A: 您可以使用 Telethon 库导出 Session String：
```python
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = YOUR_API_ID
api_hash = 'YOUR_API_HASH'

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print(client.session.save())
```

### Q: 账户被限制了怎么办？
A: 
- 检查发送频率是否过快
- 降低发送频率，增加延迟时间
- 暂停使用该账户一段时间
- 考虑更换账户

### Q: 任务执行失败怎么办？
A: 
- 检查账户状态是否正常
- 查看错误日志 `bot.log`
- 确认目标用户名/ID 是否正确
- 确认账户有权限发送消息给目标用户

### Q: 如何停止正在运行的任务？
A: 在任务列表中选择正在运行的任务，点击 "⏸️ 停止任务" 按钮。

## 🛠️ 技术栈

- **python-telegram-bot**: Telegram Bot API 框架
- **Telethon**: Telegram 客户端库
- **SQLAlchemy**: ORM 数据库框架
- **Cryptography**: 加密库
- **python-dotenv**: 环境变量管理

## 📄 许可证

MIT License

## 👥 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

如有问题，请通过 GitHub Issues 联系。

---

**⭐ 如果这个项目对您有帮助，请给个 Star！**
