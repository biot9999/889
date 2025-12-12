# Auto-Proxy Assignment Implementation

## 新需求实现 (New Requirement Implementation)

### 变更说明 (Changes)

根据新需求，代理分配策略已从**手动分配**改为**自动分配**模式：

#### 旧方式 (Old Method)
- ❌ 用户上传代理后，需要手动点击"🔄 分配代理到账户"按钮
- ❌ 代理提前分配给账户，固定使用

#### 新方式 (New Method)
- ✅ 用户上传代理后，系统自动管理代理池
- ✅ 账户连接时，自动从代理池获取可用代理
- ✅ 连接超时自动退回本地连接（无代理）
- ✅ 代理失败计数，3次失败自动禁用

---

## 实现细节 (Implementation Details)

### 1. 新增函数：`get_next_available_proxy()`

**功能**：从代理池中获取下一个可用代理

**策略**：
- 获取所有 `is_active=True` 的代理
- 按 `success_count` 升序排列（使用次数最少的优先）
- 返回使用次数最少的代理

```python
def get_next_available_proxy(db):
    active_proxies = list(db[Proxy.COLLECTION_NAME].find(
        {'is_active': True}
    ).sort('success_count', 1).limit(1))
    
    if not active_proxies:
        return None
    
    return Proxy.from_dict(active_proxies[0])
```

### 2. 更新函数：`AccountManager.get_client()`

**新逻辑**：

#### A. 检查已分配的代理
```python
if account.proxy_id:
    # 验证代理是否仍然活跃
    # 如果不活跃，清除 proxy_id
```

#### B. 自动获取代理
```python
if not proxy:
    proxy_obj = get_next_available_proxy(self.db)
    if proxy_obj:
        # 保存代理分配到账户
        self.accounts_col.update_one(
            {'_id': ObjectId(account_id)},
            {'$set': {'proxy_id': proxy_obj._id}}
        )
```

#### C. 尝试代理连接（30秒超时）
```python
try:
    client = TelegramClient(session_path, api_id, api_hash, proxy=proxy)
    await asyncio.wait_for(client.connect(), timeout=30)
    
    if await client.is_user_authorized():
        # 成功：更新 proxy.success_count
        return client
        
except asyncio.TimeoutError:
    # 超时：更新 proxy.fail_count
    # 如果失败次数 >= 3，自动禁用代理
    # 继续尝试本地连接
```

#### D. 退回本地连接
```python
# 无代理或代理失败后
client = TelegramClient(session_path, api_id, api_hash, proxy=None)
await client.connect()
```

### 3. UI 变更

#### 代理管理菜单
```
旧版本：
[📋 代理列表]
[📤 上传代理文件]
[🔄 分配代理到账户]  ← 已移除
[🗑️ 清空所有代理]

新版本：
[📋 代理列表]
[📤 上传代理文件]
[🗑️ 清空所有代理]

+ 说明文本：
💡 自动分配模式
账户登录时自动从代理池获取代理
连接超时则自动退回本地连接
```

#### 上传成功提示
```
旧版本：
✅ 代理导入完成
成功导入: 10 个
导入失败: 0 个
自动分配: 15 个账户  ← 已移除

新版本：
✅ 代理导入完成
成功导入: 10 个
导入失败: 0 个

💡 代理将在账户连接时自动分配使用
```

---

## 工作流程 (Workflow)

### 场景 1：首次使用代理

1. 管理员上传代理文件 → 代理保存到 `proxies` 集合
2. 账户尝试连接 → 调用 `get_client(account_id)`
3. 系统检查 `account.proxy_id`：无
4. 调用 `get_next_available_proxy(db)` 获取代理
5. 保存 `proxy_id` 到账户
6. 尝试使用代理连接（30秒超时）
7. 成功 → 返回客户端，`proxy.success_count += 1`
8. 失败/超时 → 尝试本地连接，`proxy.fail_count += 1`

### 场景 2：已分配代理的账户

1. 账户已有 `proxy_id`
2. 验证代理是否活跃（`is_active=True`）
3. 活跃 → 使用该代理
4. 不活跃 → 清除 `proxy_id`，重新获取

### 场景 3：代理失败处理

1. 代理连接失败 → `fail_count += 1`
2. 检查 `fail_count >= 3`
3. 是 → 设置 `is_active=False`（自动禁用）
4. 记录日志：`❌ Proxy {host}:{port} auto-disabled after 3 failures`

### 场景 4：无可用代理

1. 代理池为空或全部禁用
2. 记录日志：`No proxies available in pool, will try without proxy`
3. 直接使用本地连接（`proxy=None`）

---

## 优势 (Advantages)

### ✅ 自动化
- 无需手动分配
- 无需管理员干预
- 系统智能选择最佳代理

### ✅ 负载均衡
- 按使用次数分配（`success_count` 升序）
- 确保代理使用均匀

### ✅ 容错机制
- 超时自动退回本地
- 失败自动禁用代理
- 不影响正常业务

### ✅ 透明性
- 详细日志记录
- 成功/失败计数
- 便于监控和调试

---

## 日志示例 (Log Examples)

### 成功使用代理
```
INFO: Auto-assigned proxy to account +1234567890: 192.168.1.1:1080
INFO: Attempting connection with proxy for account +1234567890
INFO: ✅ Successfully connected with proxy: 192.168.1.1:1080
```

### 代理超时退回本地
```
WARNING: ⏱️ Proxy connection timeout after 30s, falling back to local
INFO: 🏠 Connecting locally (no proxy) for account +1234567890
```

### 代理自动禁用
```
WARNING: Proxy connection failed: TimeoutError
WARNING: ❌ Proxy 192.168.1.1:1080 auto-disabled after 3 failures
```

### 无可用代理
```
WARNING: No proxies available in pool, will try without proxy
INFO: 🏠 Connecting locally (no proxy) for account +1234567890
```

---

## 监控建议 (Monitoring Recommendations)

1. **代理健康度**
   - 定期查看代理列表中的成功/失败计数
   - 及时替换失败率高的代理

2. **代理池容量**
   - 确保代理池中有足够的活跃代理
   - 建议代理数量 ≥ 账户数量

3. **本地连接比例**
   - 监控有多少连接退回到本地
   - 比例过高说明代理质量差

4. **超时设置**
   - 当前设置：30秒
   - 可根据网络环境调整

---

## 配置参数 (Configuration)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `connection_timeout` | 30秒 | 代理连接超时时间 |
| `auto_disable_threshold` | 3次 | 自动禁用代理的失败次数 |
| `proxy_selection_strategy` | 最少使用 | 代理选择策略（按success_count升序） |

---

## 向后兼容性 (Backward Compatibility)

### ✅ 完全兼容
- 已分配 `proxy_id` 的账户继续使用该代理
- 未分配的账户自动获取代理
- `assign_proxies_to_accounts()` 函数保留但标记为废弃

### ⚠️ 废弃功能
```python
def assign_proxies_to_accounts(db):
    """
    DEPRECATED: Manual proxy assignment is no longer used.
    Proxies are now automatically assigned during account operations.
    """
    logger.warning("Manual proxy assignment is deprecated.")
    return 0
```

---

## 测试建议 (Testing Recommendations)

### 单元测试
1. ✅ `get_next_available_proxy()` - 从池中获取代理
2. ✅ 代理连接超时处理
3. ✅ 代理失败计数和自动禁用
4. ✅ 本地连接退回逻辑

### 集成测试
1. 上传代理文件 → 验证导入成功
2. 账户连接 → 验证自动分配代理
3. 代理失败 → 验证退回本地连接
4. 3次失败 → 验证代理自动禁用

### 性能测试
1. 大量账户并发连接
2. 代理池容量不足时的行为
3. 超时时间对连接速度的影响

---

## 总结 (Summary)

新的自动代理分配系统：
- ✅ 更智能：自动选择和分配
- ✅ 更可靠：超时和失败处理
- ✅ 更简单：无需手动操作
- ✅ 更灵活：动态调整和恢复

实现完全满足新需求：
> "上传代理后，机器人登录账户之前需要提前获取代理，连接代理后，操作账户时必须连接代理，如果超时则退回本地"
