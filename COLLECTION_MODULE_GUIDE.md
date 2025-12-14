# 用户采集模块使用指南

## 功能概述

用户采集模块为 Telegram 私信机器人添加了完整的用户采集功能，支持从多种渠道采集目标用户。

## 功能特性

### 五种采集类型

1. **公开群组采集** (`PUBLIC_GROUP`)
   - 采集公开群组的完整成员列表
   - 需要账户有权限查看群组成员
   - 支持大量成员的群组（使用 aggressive 模式）

2. **私有群组采集** (`PRIVATE_GROUP`)
   - 从消息历史记录中提取活跃用户
   - 适合私有群组或无法直接获取成员列表的场景
   - 支持指定消息 ID 范围

3. **频道帖子采集** (`CHANNEL_POST`)
   - 从频道帖子内容中提取用户名和 Telegram 链接
   - 支持正则表达式匹配 @username 和 t.me/username
   - 自动验证用户名有效性

4. **频道评论采集** (`CHANNEL_COMMENT`)
   - 采集频道帖子评论区的用户
   - 遍历帖子并提取评论者信息
   - 适合活跃讨论的频道

5. **关键词搜索** (`KEYWORD_SEARCH`)
   - 搜索匹配关键词的公开群组/频道
   - 从账户的对话列表中搜索
   - 返回群组/频道信息而非用户信息

### 多维度筛选

采集时可应用以下过滤器：

- ✅ **排除管理员** (`exclude_admin`) - 不采集群组管理员
- ✅ **仅高级会员** (`premium_only`) - 只采集 Telegram Premium 用户
- ✅ **必须有头像** (`has_photo`) - 只采集设置了头像的用户
- ✅ **必须有用户名** (`has_username`) - 只采集有公开用户名的用户
- ✅ **消息 ID 范围** (`min_message_id`, `max_message_id`) - 私有群组采集时指定消息范围
- ✅ **采集限制** (`message_limit`, `post_limit`, `search_limit`) - 限制处理的消息/帖子/搜索结果数量

### 账户限制

- ✅ 仅支持已上传的 **session** 或 **session+json** 格式账户
- ✅ 自动验证 session 文件存在性
- ✅ 采集任务创建时显示可用账户列表
- ❌ 不支持 tdata 格式账户（Telethon 限制）

### 结果导出

支持导出两种类型的数据：

1. **用户列表导出** (`CSV` 格式)
   - user_id - 用户 ID
   - username - 用户名
   - first_name - 名字
   - last_name - 姓氏
   - tags - 属性标签（Premium, Admin, HasPhoto）

2. **群组/频道列表导出** (`CSV` 格式)
   - group_id - 群组 ID
   - title - 标题
   - username - 用户名
   - link - 链接
   - member_count - 成员数
   - is_public - 是否公开

## 数据库结构

### Collection（采集任务）

```python
{
    '_id': ObjectId,
    'name': str,                    # 任务名称
    'collection_type': str,         # 采集类型
    'status': str,                  # 状态（pending/running/paused/completed/failed）
    'account_id': ObjectId,         # 使用的账户 ID
    'target_link': str,             # 目标链接（群组/频道）
    'keyword': str,                 # 搜索关键词
    'filters': dict,                # 过滤器配置
    'collected_users': int,         # 已采集用户数
    'collected_groups': int,        # 已采集群组数
    'created_at': datetime,         # 创建时间
    'started_at': datetime,         # 开始时间
    'completed_at': datetime,       # 完成时间
    'updated_at': datetime,         # 更新时间
    'error_message': str            # 错误信息
}
```

### CollectedUser（采集的用户）

```python
{
    '_id': ObjectId,
    'collection_id': ObjectId,      # 采集任务 ID
    'user_id': int,                 # Telegram 用户 ID
    'username': str,                # 用户名
    'first_name': str,              # 名字
    'last_name': str,               # 姓氏
    'phone': str,                   # 电话（如果可见）
    'is_premium': bool,             # 是否为高级会员
    'is_admin': bool,               # 是否为管理员
    'has_photo': bool,              # 是否有头像
    'last_seen': datetime,          # 最后在线时间
    'created_at': datetime          # 采集时间
}
```

### CollectedGroup（采集的群组）

```python
{
    '_id': ObjectId,
    'collection_id': ObjectId,      # 采集任务 ID
    'group_id': int,                # Telegram 群组 ID
    'title': str,                   # 标题
    'username': str,                # 用户名
    'link': str,                    # 链接
    'member_count': int,            # 成员数
    'is_public': bool,              # 是否公开
    'description': str,             # 描述
    'created_at': datetime          # 采集时间
}
```

## 使用流程

### 1. 访问采集菜单

从主菜单点击 **👥 采集用户** 按钮

### 2. 创建采集任务

1. 点击 **➕ 创建采集**
2. 输入任务名称
3. 选择采集类型
4. 选择使用的账户（仅显示 session 格式账户）
5. 根据采集类型输入：
   - 群组/频道链接（例如：@username 或 https://t.me/username）
   - 或搜索关键词
6. （可选）配置过滤器
7. 确认创建

### 3. 启动采集

1. 在采集列表中选择任务
2. 点击 **▶️ 开始采集**
3. 任务将在后台运行
4. 可随时点击 **⏸️ 停止采集**

### 4. 查看进度

- 采集列表显示每个任务的状态和已采集数量
- 点击任务可查看详细信息
- 任务状态实时更新

### 5. 导出结果

1. 在任务详情页面
2. 点击 **📥 导出用户** 或 **📥 导出群组**
3. 系统将生成 CSV 文件并发送

## 注意事项

### 频率限制

- 采集过程中会自动添加延迟以避免触发 Telegram 的频率限制
- 公开群组采集：每个用户 0.1 秒延迟
- 私有群组采集：每条消息 0.05 秒延迟
- 频道帖子采集：每个帖子 0.1 秒，每个用户名 0.2 秒
- 频道评论采集：每条评论 0.1 秒，每个帖子 0.2 秒
- 关键词搜索：每个结果 0.2 秒

### 权限要求

- **公开群组**：账户需要是群组成员
- **私有群组**：账户需要能查看消息历史
- **频道**：账户需要订阅频道（评论采集还需频道开启评论）
- **搜索**：账户需要有正常的访问权限

### 错误处理

常见错误及解决方法：

1. **FloodWaitError**：触发频率限制，需等待指定秒数
2. **ChatAdminRequiredError**：需要管理员权限，更换账户或目标
3. **ChannelPrivateError**：频道/群组为私有，确保账户已加入
4. **UsernameNotOccupiedError**：用户名不存在或已改变
5. **账户被限制**：账户被 Telegram 限制，需更换账户

### 性能优化

- 大型群组建议使用公开群组采集（效率更高）
- 私有群组采集受限于消息数量，建议设置合理的 `message_limit`
- 频道帖子采集会验证每个提取的用户名，速度较慢
- 使用过滤器可以显著减少采集时间和数据量

## API 参考

### CollectionManager 方法

```python
# 创建采集任务
await collection_manager.create_collection(
    name="任务名称",
    collection_type=CollectionType.PUBLIC_GROUP.value,
    account_id=ObjectId("..."),
    target_link="@groupname",
    keyword=None,
    filters={'premium_only': True, 'has_photo': True}
)

# 启动采集
await collection_manager.start_collection(collection_id)

# 停止采集
await collection_manager.stop_collection(collection_id)

# 删除采集任务及其数据
collection_manager.delete_collection(collection_id)

# 导出用户
users = await collection_manager.export_collected_users(collection_id)

# 导出群组
groups = await collection_manager.export_collected_groups(collection_id)
```

## 代码统计

### 新增文件

- `caiji.py` - 采集模块主文件（约 1400 行）

### 修改文件

- `bot.py`
  - 新增导入：7 行
  - 全局变量：1 行
  - 主菜单更新：1 行
  - 数据库索引初始化：2 行
  - 按钮处理器：88 行
  - 管理器初始化：3 行
  - 会话处理器注册：20 行
  - **总计修改：约 122 行**

### 新增内容

1. **枚举类型**（2 个）
   - `CollectionType` - 5 个采集类型
   - `CollectionStatus` - 5 个状态

2. **数据库模型**（3 个）
   - `Collection` - 采集任务模型
   - `CollectedUser` - 采集用户模型
   - `CollectedGroup` - 采集群组模型

3. **管理类**（1 个）
   - `CollectionManager` - 采集管理器（约 800 行核心逻辑）

4. **界面函数**（12 个）
   - `show_collection_menu` - 采集主菜单
   - `show_collection_list` - 任务列表
   - `show_collection_detail` - 任务详情
   - `start_create_collection` - 开始创建任务
   - `handle_collection_name` - 处理名称输入
   - `handle_collection_type` - 处理类型选择
   - `handle_collection_account` - 处理账户选择
   - `handle_collection_target` - 处理目标输入
   - `handle_collection_keyword` - 处理关键词输入
   - `show_filter_config` - 显示过滤器配置
   - `toggle_filter` - 切换过滤器
   - `create_collection_now` - 创建任务

5. **会话状态**（6 个）
   - 采集任务创建流程的状态常量

6. **辅助函数**（1 个）
   - `init_collection_indexes` - 初始化数据库索引

## 总结

用户采集模块为 Telegram 私信机器人提供了完整的用户采集解决方案，支持多种采集渠道、灵活的过滤配置和便捷的数据导出功能。模块设计遵循现有代码风格，与广告私信模块完全独立，互不干扰。
