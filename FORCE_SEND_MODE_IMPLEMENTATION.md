# Force Private Message Mode - Implementation Summary

## Overview

This document describes the implementation of the Force Private Message Mode (强制私信模式) with consecutive failure tracking and automatic account switching.

## Core Concept

Instead of counting total failures or per-user retries, this mode tracks **consecutive failures per account**. When an account reaches the consecutive failure limit, it is automatically marked as LIMITED and the system switches to the next available account.

### Key Behavior

```
Account A working:
  User 1 → ✅ Success (consecutive failures: 0)
  User 2 → ❌ Failure (consecutive failures: 1)
  User 3 → ❌ Failure (consecutive failures: 2)
  User 4 → ✅ Success (consecutive failures: 0) ← Reset!
  User 5 → ❌ Failure (consecutive failures: 1)
  ...
  User X → ❌ Failure (consecutive failures: 30)
     ↓
  🛑 Account A stopped (marked LIMITED)
  🔄 Automatically switch to Account B
```

## Implementation Details

### 1. Target Model Enhancement

Added new fields to track failure state:

```python
class Target:
    # Existing fields
    task_id: str
    username: str
    user_id: str
    is_sent: bool
    sent_at: datetime
    
    # New fields for force send mode
    failed_accounts: list = []      # List of account IDs that failed
    last_error: str = None          # Categorized error message
    retry_count: int = 0            # Total retry attempts
    last_account_id: str = None     # Last account that tried
    updated_at: datetime = None     # Last update timestamp
```

### 2. Task Configuration

Uses existing fields with new semantics:

```python
class Task:
    force_private_mode: bool = False           # Enable force send mode
    ignore_bidirectional_limit: int = 30       # Consecutive failure limit
    # When force_private_mode=True, ignore_bidirectional_limit
    # means "consecutive failures" not "total retries"
```

### 3. Execution Logic

#### Main Method: `_execute_force_send_mode()`

```python
async def _execute_force_send_mode(self, task_id, task, targets, accounts, stop_event):
    consecutive_limit = task.ignore_bidirectional_limit or DEFAULT_CONSECUTIVE_FAILURE_LIMIT
    
    for account in accounts:
        consecutive_failures = 0  # Reset for each account
        
        available_targets = self._get_available_targets_for_account(
            task_id, str(account._id), targets
        )
        
        for target in available_targets:
            success = await self._send_message_with_stop_check(task, target, account, stop_event)
            
            if success:
                consecutive_failures = 0  # Reset counter
            else:
                consecutive_failures += 1
                # Record failure
                self.targets_col.update_one(
                    {'_id': target._id},
                    {
                        '$addToSet': {'failed_accounts': str(account._id)},
                        '$set': {
                            'last_error': target.last_error,
                            'last_account_id': str(account._id),
                            'updated_at': datetime.utcnow()
                        },
                        '$inc': {'retry_count': 1}
                    }
                )
                
                # Check limit
                if consecutive_failures >= consecutive_limit:
                    # Mark account as LIMITED and switch
                    self.db[Account.COLLECTION_NAME].update_one(
                        {'_id': account._id},
                        {'$set': {'status': AccountStatus.LIMITED.value}}
                    )
                    break  # Switch to next account
```

#### Smart Target Selection: `_get_available_targets_for_account()`

Prioritizes targets for maximum success rate:

```python
def _get_available_targets_for_account(self, task_id, account_id, targets):
    never_tried = []        # Priority 1: Never tried by any account
    failed_by_others = []   # Priority 2: Failed by others, not by this account
    
    for t in targets:
        if t.is_sent:
            continue
        
        failed_accounts = getattr(t, 'failed_accounts', [])
        
        if not failed_accounts:
            never_tried.append(t)
        elif account_id not in failed_accounts:
            failed_by_others.append(t)
    
    return never_tried + failed_by_others  # Prioritized order
```

### 4. Error Categorization

The `_send_message()` method categorizes errors and stores them in `target.last_error`:

| Error Type | Category | Message |
|------------|----------|---------|
| UserIsBlockedError | 账户被封禁 | Account is blocked |
| ChatWriteForbiddenError | 账户隐私限制（对方设置了隐私保护） | Privacy settings |
| UserPrivacyRestrictedError | 双向限制（需先添加好友） | Mutual contact required |
| UserNotMutualContactError | 双向限制（需先添加好友） | Mutual contact required |
| FloodWaitError | 账户已被限流（需等待{seconds}秒） | Rate limited |
| PeerFloodError | 账户已被限流（对方无法接收消息） | Peer flood |
| "No user has" | 用户不存在 | User not found |
| "ALLOW_PAYMENT_REQUIRED" | 双向限制（需先添加好友） | Payment/verification required |
| Other | 其他错误 | Other error |

### 5. Failure Reporting

#### Text Report: `generate_failed_targets_report()`

Groups failures by error type:

```
❌ 失败用户报告

总计失败: 45 个用户

账户隐私限制（对方设置了隐私保护）: 20个
  用户: user1, user2, user3, user4, user5
  ... 还有 15 个

用户不存在: 15个
  用户: invalid1, invalid2, invalid3, invalid4, invalid5
  ... 还有 10 个

双向限制（需先添加好友）: 10个
  用户: locked1, locked2, locked3, locked4, locked5
  ... 还有 5 个
```

#### CSV Export: `export_failed_targets_csv()`

Exports detailed data:

```csv
用户名,用户ID,失败原因,尝试次数,失败账号数
user1,123456,账户隐私限制（对方设置了隐私保护）,2,2
user2,234567,用户不存在,1,1
user3,345678,双向限制（需先添加好友）,3,3
```

Uses Python's `csv` module for proper escaping and Excel compatibility (utf-8-sig encoding with BOM).

### 6. Integration with Task Execution

The execution flow checks for force_private_mode first:

```python
async def _execute_task(self, task_id, stop_event):
    # ... setup code ...
    
    # Choose execution mode
    if task.force_private_mode:
        # Force send mode: consecutive failure tracking
        await self._execute_force_send_mode(task_id, task, targets, accounts, stop_event)
    elif task.repeat_send:
        # Repeat send mode: all accounts send to all users
        await self._execute_repeat_send_mode(task_id, task, targets, accounts, stop_event)
    else:
        # Normal mode: try multiple accounts per user
        await self._execute_normal_mode(task_id, task, targets, accounts, stop_event)
```

## Bug Fixes

### Fixed Non-Responsive Configuration Buttons

Three buttons were not responding because they were missing from `button_handler()`:

1. **线程数** (Thread count) - `cfg_thread_`
2. **间隔** (Interval) - `cfg_interval_`
3. **无视双向** (Ignore bidirectional) - `cfg_bidirect_`

**Fix**: Added handlers to `button_handler()`:

```python
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... other handlers ...
    
    # New configuration handlers
    elif data.startswith('cfg_thread_') and not data.startswith('cfg_thread_interval_'):
        await request_thread_config(update, context)
    elif data.startswith('cfg_interval_'):
        await request_interval_config(update, context)
    elif data.startswith('cfg_bidirect_'):
        await request_bidirect_config(update, context)
```

## Configuration Constants

Defined in `bot.py`:

```python
# Error message truncation lengths
ERROR_MESSAGE_SHORT_LENGTH = 50   # For short error previews
ERROR_MESSAGE_LONG_LENGTH = 100   # For detailed error messages

# Force send mode defaults
DEFAULT_CONSECUTIVE_FAILURE_LIMIT = 30  # Default consecutive failures
DEFAULT_ERROR_MESSAGE = "未知错误"       # Default error message
```

## Usage Example

### 1. Enable Force Send Mode

In the task configuration UI, toggle "强制私信模式" (Force Private Mode).

### 2. Set Consecutive Failure Limit

Set "无视双向" (Ignore Bidirectional) to desired limit (e.g., 30).

### 3. Start Task

The system will:
1. Use Account A until 30 consecutive failures
2. Mark Account A as LIMITED
3. Switch to Account B
4. Continue with Account B
5. Generate detailed failure report at end

### 4. Review Results

At task completion, you'll receive:
- Standard completion report
- Failure report grouped by error type (if force_private_mode enabled)
- CSV file with detailed failure data

## Testing

All validation tests pass:

```bash
$ python3 test_force_send_mode.py

✅ PASSED: Target Model
✅ PASSED: TaskManager Methods
✅ PASSED: Task Model
✅ PASSED: Button Handlers

✅ All tests passed!
```

Security scan:
```
CodeQL Analysis: 0 security alerts
```

## Benefits

1. **Efficient Account Usage**: Automatically switches when account hits limits
2. **Smart Prioritization**: Tries never-attempted users first
3. **Detailed Tracking**: Knows exactly which accounts failed for each user
4. **Clear Reporting**: Understand why messages fail
5. **Automatic Recovery**: Next account can succeed where previous failed

## Technical Notes

### Database Schema Updates

No migration needed - new fields have default values:
- `failed_accounts`: defaults to empty list `[]`
- `last_error`: defaults to `None`
- `retry_count`: defaults to `0`
- `last_account_id`: defaults to `None`
- `updated_at`: defaults to `None`

### Performance Considerations

- Optimized `getattr()` calls to avoid repeated lookups
- Uses bulk queries for target selection
- Efficient list comprehensions for filtering

### Edge Cases Handled

1. **No available targets for account**: Skip to next account
2. **Stop signal during execution**: Gracefully exit
3. **Account daily limit reached**: Skip to next account
4. **All accounts exhausted**: Task completes with remaining targets
5. **Database connection issues**: Logged and handled

## Future Enhancements

Possible improvements for future consideration:

1. Add UI to view per-target failure history
2. Allow manual retry of failed targets with specific accounts
3. Add account "cooldown" period before reusing LIMITED accounts
4. Export failure patterns for account quality analysis
5. Add notification when account reaches warning threshold (e.g., 20/30 failures)

---

**Implementation Date**: 2025-12-19
**Status**: ✅ Complete and Tested
**Security**: ✅ No vulnerabilities (CodeQL scan passed)
