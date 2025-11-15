#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补货通知功能诊断工具
Restock Notification Feature Diagnostic Tool

使用方法 / Usage:
    python3 diagnose_restock.py

或在代理机器人启动时添加以下代码来查看配置：
Or add this code when starting the agent bot to see configuration:
    from agent_bot import AgentBotConfig
    config = AgentBotConfig()
    print("HEADQUARTERS_NOTIFY_CHAT_ID:", config.HEADQUARTERS_NOTIFY_CHAT_ID)
    print("AGENT_RESTOCK_NOTIFY_CHAT_ID:", config.AGENT_RESTOCK_NOTIFY_CHAT_ID)
    print("RESTOCK_KEYWORDS:", config.RESTOCK_KEYWORDS)
"""

import os
import sys
from pathlib import Path

# 添加父目录到路径，以便导入agent_bot模块
sys.path.insert(0, str(Path(__file__).parent / "agent"))

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ 已加载环境文件: {env_path}\n")
    else:
        print(f"⚠️ 未找到 .env 文件，使用系统环境变量\n")
except Exception as e:
    print(f"⚠️ 加载环境文件失败: {e}\n")

print("=" * 70)
print("补货通知功能配置诊断")
print("Restock Notification Configuration Diagnostic")
print("=" * 70)

# 检查环境变量
print("\n📋 环境变量检查 / Environment Variables Check:\n")

hq_chat_id = os.getenv("HQ_NOTIFY_CHAT_ID") or os.getenv("HEADQUARTERS_NOTIFY_CHAT_ID")
agent_notify_id = os.getenv("AGENT_NOTIFY_CHAT_ID")
agent_restock_id = os.getenv("AGENT_RESTOCK_NOTIFY_CHAT_ID")
keywords = os.getenv("RESTOCK_KEYWORDS", "补货通知,库存更新,新品上架,restock,new stock,inventory update")
rewrite_buttons = os.getenv("RESTOCK_REWRITE_BUTTONS", "0")

# 1. HEADQUARTERS_NOTIFY_CHAT_ID
if hq_chat_id:
    print(f"✅ HEADQUARTERS_NOTIFY_CHAT_ID: {hq_chat_id}")
    try:
        int_id = int(hq_chat_id)
        if int_id < 0:
            print(f"   ✅ 格式正确（负数，表示群组/频道）")
        else:
            print(f"   ⚠️ 警告：通常群组/频道ID应该是负数")
    except ValueError:
        print(f"   ❌ 错误：无法转换为整数")
else:
    print(f"❌ HEADQUARTERS_NOTIFY_CHAT_ID: 未设置")
    print(f"   请设置环境变量 HQ_NOTIFY_CHAT_ID 或 HEADQUARTERS_NOTIFY_CHAT_ID")

# 2. AGENT_NOTIFY_CHAT_ID
if agent_notify_id:
    print(f"\n✅ AGENT_NOTIFY_CHAT_ID: {agent_notify_id}")
else:
    print(f"\n❌ AGENT_NOTIFY_CHAT_ID: 未设置")

# 3. AGENT_RESTOCK_NOTIFY_CHAT_ID
target_id = agent_restock_id or agent_notify_id
if agent_restock_id:
    print(f"\n✅ AGENT_RESTOCK_NOTIFY_CHAT_ID: {agent_restock_id} (专用补货通知群)")
elif agent_notify_id:
    print(f"\n⚠️ AGENT_RESTOCK_NOTIFY_CHAT_ID: 未设置，将使用 AGENT_NOTIFY_CHAT_ID ({agent_notify_id})")
else:
    print(f"\n❌ AGENT_RESTOCK_NOTIFY_CHAT_ID 和 AGENT_NOTIFY_CHAT_ID: 都未设置")
    print(f"   补货通知无法转发！")

# 4. RESTOCK_KEYWORDS
print(f"\n✅ RESTOCK_KEYWORDS: {keywords}")
keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
print(f"   关键词列表（{len(keyword_list)}个）:")
for i, kw in enumerate(keyword_list, 1):
    print(f"   {i}. '{kw}'")

# 5. RESTOCK_REWRITE_BUTTONS
print(f"\n{'✅' if rewrite_buttons in ('1', 'true', 'True') else '⚠️'} RESTOCK_REWRITE_BUTTONS: {rewrite_buttons}")
if rewrite_buttons in ('1', 'true', 'True'):
    print(f"   按钮重写已启用")
else:
    print(f"   按钮重写已禁用（默认）")

# 配置总结
print("\n" + "=" * 70)
print("配置总结 / Configuration Summary")
print("=" * 70)

all_ok = True

if not hq_chat_id:
    print("❌ 缺少 HEADQUARTERS_NOTIFY_CHAT_ID - 无法监听总部消息")
    all_ok = False

if not target_id:
    print("❌ 缺少 AGENT_RESTOCK_NOTIFY_CHAT_ID 或 AGENT_NOTIFY_CHAT_ID - 无法转发消息")
    all_ok = False

if not keyword_list:
    print("❌ 没有配置关键词 - 无法匹配补货消息")
    all_ok = False

if all_ok:
    print("\n✅ 配置检查通过！")
    print(f"\n补货通知转发路径:")
    print(f"   {hq_chat_id} (总部) → {target_id} (代理)")
    print(f"\n匹配关键词（{len(keyword_list)}个）:")
    for kw in keyword_list:
        print(f"   • {kw}")
else:
    print("\n❌ 配置存在问题，请检查上述错误")

# 功能测试建议
print("\n" + "=" * 70)
print("测试建议 / Testing Recommendations")
print("=" * 70)
print("""
1. 确认机器人权限：
   - 总部群: 机器人是成员，有读取消息权限
   - 代理群: 机器人是管理员或有发送消息/媒体权限

2. 在总部群发送测试消息：
   例如: "测试补货通知：新品上架！"
   
3. 检查机器人日志：
   应该看到类似以下日志：
   
   INFO - 🔍 收到群组/频道消息: chat_id=-1001234567890, ...
   INFO - ✅ 消息来自总部通知群 -1001234567890
   INFO - 🔔 检测到补货通知（关键词: 补货通知）: 测试补货通知...
   INFO - ✅ 补货通知已镜像到 -1009876543210 (message_id: 12345)

4. 如果没有日志输出：
   - 检查 HEADQUARTERS_NOTIFY_CHAT_ID 是否正确
   - 检查机器人是否在总部群中
   - 检查消息是否包含配置的关键词

5. 如果有日志但没有转发：
   - 检查 copy_message 是否失败（权限问题）
   - 检查 AGENT_RESTOCK_NOTIFY_CHAT_ID 配置
   - 检查代理群的机器人权限
""")

print("=" * 70)
print("诊断完成 / Diagnostic Complete")
print("=" * 70)
