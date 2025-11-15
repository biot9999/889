# 补货通知功能故障排查指南
# Restock Notification Troubleshooting Guide

## 问题：总部发了补货通知，代理群没有收到

### 第一步：运行诊断脚本

```bash
cd /home/runner/work/889/889
python3 diagnose_restock.py
```

这会检查你的所有配置是否正确。

---

### 第二步：检查环境变量配置

确保以下环境变量已正确设置（在 `.env` 文件或系统环境变量中）：

#### 必需配置：

```bash
# 总部通知群ID（从哪里监听）
HEADQUARTERS_NOTIFY_CHAT_ID=-1001234567890
# 或者
HQ_NOTIFY_CHAT_ID=-1001234567890

# 代理通知群ID（往哪里发送）
AGENT_NOTIFY_CHAT_ID=-1009876543210
```

#### 可选配置：

```bash
# 专用补货通知群（如果不设置，会用 AGENT_NOTIFY_CHAT_ID）
AGENT_RESTOCK_NOTIFY_CHAT_ID=-1009876543211

# 补货关键词（默认已包含常用词）
RESTOCK_KEYWORDS=补货通知,库存更新,新品上架,restock,new stock,inventory update
```

#### 如何获取 chat_id？

1. 将 @userinfobot 添加到你的群组
2. 在群组中发送任意消息
3. 转发该消息给 @userinfobot
4. Bot 会告诉你 chat_id

---

### 第三步：检查机器人权限

#### 总部通知群：
- ✅ 机器人已添加为成员
- ✅ 机器人有读取消息权限

#### 代理补货通知群：
- ✅ 机器人已添加为成员或管理员
- ✅ 机器人有"发送消息"权限
- ✅ 机器人有"发送媒体"权限（如果要转发图片/视频）

---

### 第四步：重启机器人并查看日志

重启代理机器人后，日志应该显示：

```
INFO - ✅ 处理器设置完成
```

然后在总部群发送测试消息（包含关键词）：

```
测试补货通知：新品到货！
```

#### 正常情况下的日志输出：

```
INFO - 🔍 收到群组/频道消息: chat_id=-1001234567890, chat_type=channel, title=总部补货通知
INFO - ✅ 消息来自总部通知群 -1001234567890
INFO - 🔔 检测到补货通知（关键词: 补货通知）: 测试补货通知：新品到货！...
INFO - ✅ 补货通知已镜像到 -1009876543210 (message_id: 12345)
```

---

### 第五步：根据日志诊断问题

#### 情况 1：没有看到 "收到群组/频道消息" 日志

**可能原因：**
- 机器人不在总部通知群中
- HEADQUARTERS_NOTIFY_CHAT_ID 配置错误

**解决方案：**
1. 确认机器人已加入总部通知群
2. 运行 `diagnose_restock.py` 检查配置
3. 确认 chat_id 是负数（群组/频道ID都是负数）

#### 情况 2：看到 "收到群组/频道消息" 但显示 "消息不是来自总部通知群"

**可能原因：**
- HEADQUARTERS_NOTIFY_CHAT_ID 配置的值与实际群组ID不匹配

**解决方案：**
1. 检查日志中显示的实际 chat_id
2. 对比配置的 HEADQUARTERS_NOTIFY_CHAT_ID
3. 修正配置，重启机器人

**示例日志：**
```
INFO - 🔍 收到群组/频道消息: chat_id=-1001234567890, ...
DEBUG - 🔍 比较: chat_id=-1001234567890, hq_chat_id=-1009999999999, 匹配=False
DEBUG - ⚠️ 消息不是来自总部通知群（来自 -1001234567890，期望 -1009999999999）
```

修正配置：
```bash
HEADQUARTERS_NOTIFY_CHAT_ID=-1001234567890  # 使用实际的 chat_id
```

#### 情况 3：看到 "消息来自总部通知群" 但显示 "消息不包含补货关键词"

**可能原因：**
- 消息文本不包含配置的任何关键词

**解决方案：**
1. 查看日志中的 "配置的关键词" 列表
2. 确认测试消息包含至少一个关键词
3. 如需添加自定义关键词：

```bash
RESTOCK_KEYWORDS=补货通知,库存更新,新品上架,补货,上新,到货
```

#### 情况 4：检测到补货通知，但显示 "AGENT_RESTOCK_NOTIFY_CHAT_ID 未配置"

**可能原因：**
- 没有设置 AGENT_RESTOCK_NOTIFY_CHAT_ID
- 也没有设置 AGENT_NOTIFY_CHAT_ID

**解决方案：**
至少设置其中一个：

```bash
AGENT_NOTIFY_CHAT_ID=-1009876543210
# 或
AGENT_RESTOCK_NOTIFY_CHAT_ID=-1009876543211
```

#### 情况 5：检测到补货通知，但 copy_message 失败

**日志示例：**
```
INFO - 🔔 检测到补货通知（关键词: 补货通知）: ...
WARNING - ⚠️ copy_message 失败（可能是权限问题）: Bad Request: not enough rights to send text messages to the chat
INFO - 🔄 尝试使用 send_message 回退方案...
```

**可能原因：**
- 机器人在代理群没有发送消息权限

**解决方案：**
1. 将机器人设为管理员，或
2. 给机器人以下权限：
   - 发送消息
   - 发送媒体（如果要转发图片/视频）

---

### 快速诊断清单

- [ ] 运行了 `diagnose_restock.py` 脚本
- [ ] HEADQUARTERS_NOTIFY_CHAT_ID 已配置且格式正确（负数）
- [ ] AGENT_NOTIFY_CHAT_ID 或 AGENT_RESTOCK_NOTIFY_CHAT_ID 已配置
- [ ] 机器人在总部通知群中（可以看到群消息）
- [ ] 机器人在代理补货通知群中（有发送权限）
- [ ] 测试消息包含配置的关键词
- [ ] 重启了机器人
- [ ] 查看了机器人日志输出

---

### 还是不工作？

如果按照上述步骤检查后仍然不工作，请提供以下信息：

1. **诊断脚本输出：**
   ```bash
   python3 diagnose_restock.py > diagnostic.txt 2>&1
   ```

2. **机器人日志（发送测试消息时的日志）：**
   - 包含时间戳的完整日志
   - 特别是包含 🔍、✅、⚠️ 等符号的日志行

3. **配置信息（隐藏敏感数据）：**
   - HEADQUARTERS_NOTIFY_CHAT_ID: -100xxxxxxxxx
   - AGENT_RESTOCK_NOTIFY_CHAT_ID: -100xxxxxxxxx
   - RESTOCK_KEYWORDS: (你配置的关键词)

4. **测试消息内容：**
   - 在总部群发送的完整消息文本

---

### 更新内容（2025-01-15）

本次更新改进了以下内容：

✅ **增强调试日志**
- 现在会记录所有接收到的群组/频道消息
- 显示 chat_id、chat_type 和群组标题
- 记录关键词匹配详情

✅ **改进消息过滤器**
- 使用更可靠的过滤器匹配所有非私聊消息
- 处理器顺序优化，确保群组消息优先处理

✅ **新增诊断工具**
- `diagnose_restock.py` 脚本帮助检查配置
- 自动验证所有环境变量
- 提供详细的测试建议

---

**如有问题，请联系：**
- Telegram: @9haokf
- GitHub Issues: https://github.com/biot9999/889/issues
