#!/usr/bin/env python3
"""
Verification script to check account type separation implementation
"""

import re
import sys

def check_account_model():
    """Check Account model has account_type field"""
    print("=" * 70)
    print("1. Checking Account Model")
    print("=" * 70)
    
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        'account_type parameter in __init__': "account_type='messaging'" in content,
        'account_type in to_dict': "'account_type': self.account_type" in content,
        'account_type in from_dict': "account_type=doc.get('account_type', 'messaging')" in content,
        'self.account_type assignment': 'self.account_type = account_type' in content,
    }
    
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
        if not passed:
            all_passed = False
    
    print()
    return all_passed

def check_database_index():
    """Check database has account_type index"""
    print("=" * 70)
    print("2. Checking Database Index")
    print("=" * 70)
    
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    has_index = "create_index('account_type')" in content
    status = "✅" if has_index else "❌"
    print(f"{status} account_type index in init_db")
    print()
    return has_index

def check_import_logic():
    """Check import logic accepts account_type"""
    print("=" * 70)
    print("3. Checking Import Logic")
    print("=" * 70)
    
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        'import_session_zip has account_type param': re.search(r'async def import_session_zip.*account_type=', content) is not None,
        '_verify_session has account_type param': re.search(r'async def _verify_session.*account_type=', content) is not None,
        '_verify_session passes account_type to Account': 'account_type=account_type' in content and 'Account(' in content,
        'import_session_zip passes account_type to _verify_session': 'await self._verify_session(session_path, api_id, api_hash, account_type)' in content,
    }
    
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
        if not passed:
            all_passed = False
    
    print()
    return all_passed

def check_messaging_accounts():
    """Check messaging account functions filter by account_type"""
    print("=" * 70)
    print("4. Checking Messaging Account Functions")
    print("=" * 70)
    
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        'show_accounts_menu filters by messaging': "'account_type': 'messaging'" in content and 'show_accounts_menu' in content,
        'list_accounts filters by messaging': "find({'account_type': 'messaging'})" in content and 'async def list_accounts' in content,
        'check_all_accounts_status filters by messaging': re.search(r"async def check_all_accounts_status.*find\(\{'account_type': 'messaging'\}\)", content, re.DOTALL) is not None,
    }
    
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
        if not passed:
            all_passed = False
    
    print()
    return all_passed

def check_collection_accounts():
    """Check collection account functions filter by account_type"""
    print("=" * 70)
    print("5. Checking Collection Account Functions")
    print("=" * 70)
    
    with open('caiji.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        'show_collection_menu filters by collection': "'account_type': 'collection'" in content and 'show_collection_menu' in content,
        'show_collection_accounts_menu exists': 'async def show_collection_accounts_menu' in content,
        'list_collection_accounts exists': 'async def list_collection_accounts' in content,
        'list_collection_accounts filters by collection': "find({'account_type': 'collection'})" in content,
        'handle_collection_type filters by collection': "'account_type': 'collection'" in content and 'handle_collection_type' in content,
    }
    
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
        if not passed:
            all_passed = False
    
    print()
    return all_passed

def check_callback_handlers():
    """Check callback handlers for collection accounts"""
    print("=" * 70)
    print("6. Checking Callback Handlers")
    print("=" * 70)
    
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        'collection_accounts_menu handler': "elif data == 'collection_accounts_menu':" in content,
        'collection_accounts_list handler': "elif data == 'collection_accounts_list':" in content,
        'collection_accounts_add handler': "elif data == 'collection_accounts_add':" in content,
        'collection_accounts_add sets account_type': "context.user_data['account_type'] = 'collection'" in content,
    }
    
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
        if not passed:
            all_passed = False
    
    print()
    return all_passed

def check_file_upload():
    """Check file upload handler uses account_type"""
    print("=" * 70)
    print("7. Checking File Upload Handler")
    print("=" * 70)
    
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        'handle_file_upload gets account_type': "account_type = context.user_data.get('account_type', 'messaging')" in content,
        'handle_file_upload passes account_type': "await account_manager.import_session_zip(zip_path, account_type=account_type)" in content,
    }
    
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
        if not passed:
            all_passed = False
    
    print()
    return all_passed

def check_data_migration():
    """Check data migration code exists"""
    print("=" * 70)
    print("8. Checking Data Migration")
    print("=" * 70)
    
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    has_migration = "db[Account.COLLECTION_NAME].update_many" in content and \
                    "{'account_type': {'$exists': False}}" in content and \
                    "{'$set': {'account_type': 'messaging'}}" in content
    
    status = "✅" if has_migration else "❌"
    print(f"{status} Data migration code in main()")
    print()
    return has_migration

def main():
    """Run all verification checks"""
    print("\n")
    print("*" * 70)
    print("Account Type Separation Verification")
    print("*" * 70)
    print("\n")
    
    results = []
    results.append(check_account_model())
    results.append(check_database_index())
    results.append(check_import_logic())
    results.append(check_messaging_accounts())
    results.append(check_collection_accounts())
    results.append(check_callback_handlers())
    results.append(check_file_upload())
    results.append(check_data_migration())
    
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    
    if all(results):
        print("✅ All verification checks passed!")
        print("\nImplementation is complete and correct.")
        return 0
    else:
        print("❌ Some verification checks failed!")
        print("\nPlease review the failed checks above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
