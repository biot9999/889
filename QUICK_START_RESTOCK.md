# 补货通知自动镜像 - 快速开始指南
# Restock Notification Mirroring - Quick Start Guide

## 中文版 / Chinese Version

### 5分钟快速配置

#### 步骤 1：获取频道/群组 ID

使用 **@userinfobot**：
1. 将 @userinfobot 添加到你的群组/频道
2. 在群组中发送任意消息
3. 转发该消息给 @userinfobot
4. Bot 会回复消息所在群组的 chat_id

示例回复：
```
Chat
Id: -1001234567890
Type: supergroup
Title: 总部补货通知群
```

你需要获取两个 ID：
- **总部通知群 ID**（HEADQUARTERS_NOTIFY_CHAT_ID）
- **代理补货通知群 ID**（AGENT_RESTOCK_NOTIFY_CHAT_ID）

#### 步骤 2：配置环境变量

编辑你的 `.env` 文件，添加：

```bash
# 总部通知群（监听补货消息）
HEADQUARTERS_NOTIFY_CHAT_ID=-1001234567890

# 代理通知群（发送补货消息）
AGENT_NOTIFY_CHAT_ID=-1009876543210
```

或者使用专用补货频道：

```bash
# 总部通知群
HEADQUARTERS_NOTIFY_CHAT_ID=-1001234567890

# 代理通用通知群
AGENT_NOTIFY_CHAT_ID=-1009876543210

# 代理专用补货通知群
AGENT_RESTOCK_NOTIFY_CHAT_ID=-1009876543211
```

#### 步骤 3：配置机器人权限

**总部通知群**：
- ✅ 将代理机器人添加为成员
- ✅ 确保机器人可以读取消息

**代理补货通知群**：
- ✅ 将代理机器人添加为成员/管理员
- ✅ 给予"发送消息"权限
- ✅ 给予"发送媒体"权限（如果要转发图片/视频）

#### 步骤 4：启动机器人

```bash
python3 agent/agent_bot.py
```

#### 步骤 5：测试功能

1. 在总部通知群发送包含关键词的测试消息：
   ```
   🎉 补货通知：TG账号大量到货！
   ```

2. 检查代理补货通知群是否收到转发的消息

3. 查看机器人日志：
   ```
   INFO - 🔔 检测到补货通知（关键词: 补货通知）: 🎉 补货通知：TG账号大量到货！...
   INFO - ✅ 补货通知已镜像到 -1009876543210 (message_id: 12345)
   ```

### 可选配置

#### 自定义关键词

如果总部使用不同的关键词，可以自定义：

```bash
RESTOCK_KEYWORDS=补货,上新,到货,新货,库存补充
```

#### 启用按钮重写

如果需要重写HQ消息的按钮，使其指向代理机器人：

```bash
HQ_RESTOCK_REWRITE_BUTTONS=1
```

效果：
- 不使用 copy_message，而是发送新消息
- 附带重写的按钮："🛒 购买商品" → https://t.me/{agent_bot_username}

### 常见问题

**Q: 消息没有被转发？**

A: 检查以下几点：
1. chat_id 是否正确（注意负号）
2. 机器人是否在总部群中
3. 消息是否包含配置的关键词
4. 查看机器人日志了解具体错误

**Q: 显示权限错误？**

A: 确保：
1. 机器人在代理群中有"发送消息"权限
2. 机器人在代理群中有"发送媒体"权限
3. 如果是频道，机器人需要是管理员

**Q: 只想转发特定关键词？**

A: 修改 `RESTOCK_KEYWORDS` 为你需要的关键词：
```bash
RESTOCK_KEYWORDS=重要补货,紧急上新
```

---

## English Version

### 5-Minute Quick Setup

#### Step 1: Get Channel/Group IDs

Use **@userinfobot**:
1. Add @userinfobot to your group/channel
2. Send any message in the group
3. Forward that message to @userinfobot
4. The bot will reply with the chat_id

Example reply:
```
Chat
Id: -1001234567890
Type: supergroup
Title: HQ Restock Notification Group
```

You need two IDs:
- **Headquarters Notification Group ID** (HEADQUARTERS_NOTIFY_CHAT_ID)
- **Agent Restock Notification Group ID** (AGENT_RESTOCK_NOTIFY_CHAT_ID)

#### Step 2: Configure Environment Variables

Edit your `.env` file and add:

```bash
# Headquarters notification group (listen for restock messages)
HEADQUARTERS_NOTIFY_CHAT_ID=-1001234567890

# Agent notification group (send restock messages)
AGENT_NOTIFY_CHAT_ID=-1009876543210
```

Or use a dedicated restock channel:

```bash
# Headquarters notification group
HEADQUARTERS_NOTIFY_CHAT_ID=-1001234567890

# Agent general notification group
AGENT_NOTIFY_CHAT_ID=-1009876543210

# Agent dedicated restock notification group
AGENT_RESTOCK_NOTIFY_CHAT_ID=-1009876543211
```

#### Step 3: Configure Bot Permissions

**Headquarters Notification Group**:
- ✅ Add agent bot as member
- ✅ Ensure bot can read messages

**Agent Restock Notification Group**:
- ✅ Add agent bot as member/admin
- ✅ Grant "Send Messages" permission
- ✅ Grant "Send Media" permission (if forwarding photos/videos)

#### Step 4: Start the Bot

```bash
python3 agent/agent_bot.py
```

#### Step 5: Test the Feature

1. Send a test message with keywords in HQ notification group:
   ```
   🎉 Restock Notice: Large batch of TG accounts available!
   ```

2. Check if the agent restock notification group receives the forwarded message

3. Check bot logs:
   ```
   INFO - 🔔 检测到补货通知（关键词: restock）: 🎉 Restock Notice: Large batch...
   INFO - ✅ 补货通知已镜像到 -1009876543210 (message_id: 12345)
   ```

### Optional Configuration

#### Custom Keywords

If headquarters uses different keywords, customize them:

```bash
RESTOCK_KEYWORDS=restock,new stock,back in stock,restocked,new arrival
```

#### Enable Button Rewriting

To rewrite HQ message buttons to point to agent bot:

```bash
HQ_RESTOCK_REWRITE_BUTTONS=1
```

Effect:
- Does NOT use copy_message, sends new message instead
- Attaches rewritten button: "🛒 购买商品" → https://t.me/{agent_bot_username}

### FAQ

**Q: Messages not being forwarded?**

A: Check:
1. Is the chat_id correct (note the minus sign)?
2. Is the bot a member of HQ group?
3. Does the message contain configured keywords?
4. Check bot logs for specific errors

**Q: Permission errors?**

A: Ensure:
1. Bot has "Send Messages" permission in agent group
2. Bot has "Send Media" permission in agent group
3. For channels, bot needs to be an admin

**Q: Want to forward only specific keywords?**

A: Modify `RESTOCK_KEYWORDS` to your needed keywords:
```bash
RESTOCK_KEYWORDS=urgent restock,priority stock
```

---

## 技术支持 / Technical Support

- 📖 详细文档 / Detailed Docs: `RESTOCK_NOTIFICATION_FEATURE.md`
- 💬 Telegram: @9haokf
- 🐛 Issues: https://github.com/biot9999/889/issues

---

## 配置检查清单 / Configuration Checklist

使用此清单确保一切配置正确：
Use this checklist to ensure everything is configured correctly:

- [ ] 已获取总部通知群 ID / Got HQ notification group ID
- [ ] 已获取代理补货通知群 ID / Got agent restock notification group ID
- [ ] 已配置 HEADQUARTERS_NOTIFY_CHAT_ID / Configured HEADQUARTERS_NOTIFY_CHAT_ID
- [ ] 已配置 AGENT_NOTIFY_CHAT_ID 或 AGENT_RESTOCK_NOTIFY_CHAT_ID / Configured AGENT_NOTIFY_CHAT_ID or AGENT_RESTOCK_NOTIFY_CHAT_ID
- [ ] 机器人已加入总部通知群 / Bot joined HQ notification group
- [ ] 机器人已加入代理补货通知群 / Bot joined agent restock notification group
- [ ] 机器人在代理群有发送消息权限 / Bot has send message permission in agent group
- [ ] 机器人在代理群有发送媒体权限 / Bot has send media permission in agent group
- [ ] 已测试发送包含关键词的消息 / Tested sending message with keywords
- [ ] 已确认消息被成功转发 / Confirmed message was forwarded successfully
- [ ] 已检查机器人日志 / Checked bot logs

---

## 下一步 / Next Steps

配置完成后，你可以：
After configuration, you can:

1. **监控日志** / **Monitor Logs**
   - 观察转发是否正常工作
   - Watch if forwarding works correctly

2. **自定义关键词** / **Customize Keywords**
   - 根据实际需求调整关键词
   - Adjust keywords based on actual needs

3. **启用高级功能** / **Enable Advanced Features**
   - 考虑是否需要按钮重写
   - Consider if button rewriting is needed

4. **设置专用频道** / **Set Up Dedicated Channel**
   - 创建专门的补货通知频道
   - Create dedicated restock notification channel

5. **优化通知内容** / **Optimize Notification Content**
   - 与总部协调使用统一的关键词
   - Coordinate with HQ to use unified keywords
