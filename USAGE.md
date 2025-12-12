# 使用示例

## 快速开始示例

### 1. 配置环境

编辑 `.env` 文件：

```env
# Bot Token - 从 @BotFather 获取
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# 管理员用户 ID - 你的 Telegram 用户 ID
# 可以通过 @userinfobot 获取
ADMIN_USER_ID=123456789

# Telegram API 凭证 - 从 https://my.telegram.org 获取
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890

# MongoDB 数据库配置
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=telegram_bot

# 任务配置
DEFAULT_MIN_INTERVAL=30    # 最小发送间隔（秒）
DEFAULT_MAX_INTERVAL=120   # 最大发送间隔（秒）
DEFAULT_DAILY_LIMIT=50     # 每账户每日发送限制
```

### 2. 启动机器人

```bash
# 方法 1：使用启动脚本（推荐）
./start.sh

# 方法 2：手动启动
python3 bot.py
```

### 3. 使用 Bot

#### 3.1 添加账户

1. 在 Telegram 中打开你的 Bot
2. 发送 `/start`
3. 点击 "📱 账户管理"
4. 点击 "➕ 添加账户"
5. 选择 "📁 上传 Session 文件"
6. 上传包含 `.session` 文件的 zip 包

**支持的文件格式：**
- 纯 `.session` 文件
- `.session` + `.json` 文件（包含 API 凭证）
- `tdata` 文件夹（Telegram Desktop）

#### 3.2 创建任务

1. 点击 "📝 任务管理"
2. 点击 "➕ 创建新任务"
3. 输入任务名称，例如：`测试推广`
4. 输入消息内容，可以使用变量：
   ```
   你好 {name}！
   
   这是一条测试消息。
   
   {full_name}，欢迎访问我们的网站：https://example.com
   ```

5. 选择消息格式：
   - 📝 纯文本
   - 📌 Markdown
   - 🏷️ HTML

6. 选择媒体类型：
   - 📝 纯文本
   - 🖼️ 图片
   - 🎥 视频
   - 📄 文档

7. 添加目标用户（两种方式）：
   
   **方式 1：直接输入**
   ```
   @username1
   @username2
   username3
   123456789
   ```
   
   **方式 2：上传 txt 文件**
   创建 `targets.txt`：
   ```
   @user1
   @user2
   user3
   123456789
   # 这是注释，会被忽略
   @user4
   ```

#### 3.3 开始任务

1. 点击 "📝 任务管理" → "📋 查看任务列表"
2. 找到你的任务，点击 "▶️ 开始"
3. 机器人会自动：
   - 分配活跃账户
   - 验证目标用户
   - 发送个性化消息
   - 处理错误和重试
   - 实时更新进度

#### 3.4 监控进度

点击任务的 "📊 进度" 按钮查看：
- 总目标数
- 已发送数量
- 失败数量
- 待发送数量
- 完成百分比

#### 3.5 导出结果

任务完成后，点击 "📥 导出" 获取三个文件：

1. **success.txt** - 成功发送的用户列表
   ```
   @user1
   @user2
   user3
   ```

2. **failed.txt** - 失败的用户及原因
   ```
   @user4: Privacy error: UserPrivacyRestrictedError
   @user5: User not found
   ```

3. **log.txt** - 详细发送日志
   ```
   [2024-12-11 10:30:15] 成功: OK
   [2024-12-11 10:32:45] 失败: Privacy error
   [2024-12-11 10:35:20] 成功: OK
   ```

## 高级示例

### 消息个性化变量

```
嗨 {name}！👋

很高兴认识你，{full_name}。

我想邀请你加入我们的社群。

如果你感兴趣，请联系 {username}。
```

**变量说明：**
- `{name}` - 自动使用用户名或名字
- `{first_name}` - 用户的名字
- `{last_name}` - 用户的姓氏
- `{full_name}` - 完整姓名（名+姓）
- `{username}` - @用户名

### Markdown 格式示例

```markdown
**重要通知**

你好 {name}！

我们有一个*特别优惠*给你：

• 优惠1
• 优惠2
• 优惠3

点击 [这里](https://example.com) 了解更多！

使用代码 `SPECIAL2024` 获取折扣。
```

### HTML 格式示例

```html
<b>特别推广</b>

你好 {name}！

我们为 <i>{full_name}</i> 准备了特别优惠。

<b>主要特点：</b>
• 功能1
• 功能2
• 功能3

<a href="https://example.com">立即访问</a>

<code>优惠码：PROMO2024</code>
```

### 带图片的消息

1. 选择媒体类型："🖼️ 图片"
2. 上传图片文件
3. 输入图片说明（支持变量）：
   ```
   嗨 {name}！

   这是我们的新产品图片。

   查看更多：https://example.com
   ```

### 批量导入目标

创建 `targets.txt`：
```
# VIP 用户
@vipuser1
@vipuser2

# 普通用户
@user1
@user2
@user3

# 通过 ID
123456789
987654321

# 这些会被忽略
# @blockeduser
```

## 常见问题

### Q: 如何获取 Session 文件？

**方法 1：使用现有客户端**
- Telegram Desktop：复制 `tdata` 文件夹
- 其他客户端：导出 session 文件

**方法 2：使用脚本生成**
```python
from telethon import TelegramClient

api_id = "your_api_id"
api_hash = "your_api_hash"
phone = "+1234567890"

client = TelegramClient("session_name", api_id, api_hash)
client.start(phone)
```

### Q: 如何避免被封号？

1. **使用合理的发送间隔**：建议 30-120 秒
2. **限制每日发送数量**：建议每账户 ≤ 50 条
3. **使用多个小号**：不要用主账号
4. **避免垃圾内容**：发送有价值的信息
5. **尊重用户隐私**：不要骚扰用户

### Q: 账户显示 "limited" 状态怎么办？

这表示账户被 Telegram 限制了。建议：
1. 停止使用该账户 24-48 小时
2. 降低发送频率
3. 检查消息内容是否违规
4. 使用其他账户继续任务

### Q: 任务一直卡在 "running" 状态？

可能原因：
1. 所有账户都达到每日限制
2. 网络连接问题
3. 所有目标用户都无效

解决方法：
1. 检查账户状态
2. 查看日志文件
3. 点击 "⏸️ 停止" 然后重新开始

### Q: 如何配置代理？

编辑 `.env` 文件：
```env
PROXY_ENABLED=true
PROXY_TYPE=socks5
PROXY_HOST=127.0.0.1
PROXY_PORT=1080
PROXY_USERNAME=your_username  # 可选
PROXY_PASSWORD=your_password  # 可选
```

## 最佳实践

### 1. 账户管理
- 使用专门的小号进行批量操作
- 定期检查账户状态
- 不要在同一时间使用太多账户
- 新账户需要"养号"一段时间

### 2. 任务配置
- 测试先用小量目标（5-10 个）
- 消息内容要自然、有价值
- 使用变量让消息个性化
- 避免完全相同的消息

### 3. 发送策略
- 使用随机间隔（30-120 秒）
- 限制每账户每日发送量
- 高峰时段避免大量发送
- 分散任务到多个时间段

### 4. 目标管理
- 定期清理无效用户
- 不要重复发送给同一用户
- 尊重用户的隐私设置
- 维护黑名单

### 5. 监控和优化
- 定期查看统计数据
- 分析失败原因
- 优化消息内容
- 调整发送策略

## 故障排除

### 检查日志

```bash
# 查看 bot 日志
tail -f logs/bot.log

# 查看最近 100 行
tail -n 100 logs/bot.log

# 搜索错误
grep "ERROR" logs/bot.log
```

### 重置数据库

```bash
# 备份当前数据库
cp telegram_bot.db telegram_bot.db.backup

# 删除数据库
rm telegram_bot.db

# 重新初始化
python3 init_db.py
```

### 更新依赖

```bash
# 激活虚拟环境
source venv/bin/activate

# 更新所有依赖
pip install -r requirements.txt --upgrade
```

## 技术支持

如有问题，请：
1. 查看 README.md 文档
2. 检查日志文件
3. 在 GitHub 提交 Issue
4. 提供详细的错误信息和日志
