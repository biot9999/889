# 宝塔面板部署指南 - CentOS 9

本指南将帮助您在 CentOS 9 系统的宝塔面板上部署 Telegram 私信机器人。

## 📋 前置要求

1. CentOS 9 服务器
2. 已安装宝塔面板（BT-Panel）
3. Root 或 sudo 权限

## 🔧 安装宝塔面板（如未安装）

```bash
# CentOS 9 安装宝塔面板
yum install -y wget && wget -O install.sh https://download.bt.cn/install/install_6.0.sh && sh install.sh ed8484bec
```

安装完成后，记录面板地址、用户名和密码。

## 📦 在宝塔中安装依赖

### 1. 安装 Python 环境

在宝塔面板中：
1. 进入 **软件商店**
2. 搜索 **Python 项目管理器**
3. 安装 **Python 项目管理器**
4. 安装 **Python 3.8** 或更高版本

或者通过命令行安装：
```bash
# 安装 Python 3.11
yum install -y python3.11 python3.11-pip python3.11-devel

# 验证安装
python3.11 --version
pip3.11 --version
```

### 2. 创建项目目录

```bash
# 创建项目目录
mkdir -p /www/wwwroot/telegram_bot
cd /www/wwwroot/telegram_bot

# 设置权限
chown -R www:www /www/wwwroot/telegram_bot
chmod -R 755 /www/wwwroot/telegram_bot
```

### 3. 上传项目文件

通过宝塔文件管理器上传以下文件到 `/www/wwwroot/telegram_bot/`：
- `sxbot.py`
- `requirements.txt`
- `.env.example`

或使用命令行：
```bash
cd /www/wwwroot/telegram_bot
# 如果使用 git
git clone https://github.com/yourusername/telegram-bot.git .
```

### 4. 安装 Python 依赖

```bash
cd /www/wwwroot/telegram_bot

# 创建虚拟环境
python3.11 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt

# 退出虚拟环境
deactivate
```

### 5. 配置环境变量

```bash
# 复制配置文件
cp .env.example .env

# 编辑配置文件
vi .env
```

或在宝塔面板中：
1. 进入 **文件管理**
2. 找到 `/www/wwwroot/telegram_bot/.env.example`
3. 复制为 `.env`
4. 点击编辑，填入配置信息

必须配置的项：
```env
BOT_TOKEN=你的机器人Token
API_ID=你的API_ID
API_HASH=你的API_Hash
ENCRYPTION_KEY=加密密钥
```

生成加密密钥：
```bash
cd /www/wwwroot/telegram_bot
source venv/bin/activate
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 🚀 启动机器人

### 方法 1: 使用 Supervisor（推荐）

#### 1.1 在宝塔面板安装 Supervisor
1. 进入 **软件商店**
2. 搜索 **Supervisor**
3. 点击 **安装**

#### 1.2 配置 Supervisor

在宝塔面板中：
1. 进入 **软件商店** → **Supervisor** → **设置**
2. 点击 **添加守护进程**
3. 填写配置：

```ini
名称: telegram_bot
启动用户: www
运行目录: /www/wwwroot/telegram_bot
启动命令: /www/wwwroot/telegram_bot/venv/bin/python /www/wwwroot/telegram_bot/sxbot.py
进程数量: 1
```

或者手动创建配置文件：
```bash
vi /etc/supervisor/conf.d/telegram_bot.conf
```

添加以下内容：
```ini
[program:telegram_bot]
command=/www/wwwroot/telegram_bot/venv/bin/python /www/wwwroot/telegram_bot/sxbot.py
directory=/www/wwwroot/telegram_bot
user=www
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/www/wwwroot/telegram_bot/supervisor.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
```

#### 1.3 启动服务

在宝塔 Supervisor 管理界面点击 **启动**，或使用命令：
```bash
supervisorctl reread
supervisorctl update
supervisorctl start telegram_bot
```

#### 1.4 查看状态

```bash
# 查看运行状态
supervisorctl status telegram_bot

# 查看日志
tail -f /www/wwwroot/telegram_bot/bot.log
tail -f /www/wwwroot/telegram_bot/supervisor.log
```

### 方法 2: 使用 systemd 服务

#### 2.1 创建 systemd 服务文件

```bash
vi /etc/systemd/system/telegram-bot.service
```

添加以下内容：
```ini
[Unit]
Description=Telegram Bot Service
After=network.target

[Service]
Type=simple
User=www
Group=www
WorkingDirectory=/www/wwwroot/telegram_bot
Environment="PATH=/www/wwwroot/telegram_bot/venv/bin"
ExecStart=/www/wwwroot/telegram_bot/venv/bin/python /www/wwwroot/telegram_bot/sxbot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 2.2 启动服务

```bash
# 重载 systemd
systemctl daemon-reload

# 启动服务
systemctl start telegram-bot

# 设置开机自启
systemctl enable telegram-bot

# 查看状态
systemctl status telegram-bot

# 查看日志
journalctl -u telegram-bot -f
```

### 方法 3: 使用 Screen（临时测试）

```bash
# 安装 screen
yum install -y screen

# 创建会话
screen -S telegram_bot

# 激活虚拟环境并启动
cd /www/wwwroot/telegram_bot
source venv/bin/activate
python sxbot.py

# 按 Ctrl+A+D 退出会话但保持运行

# 重新连接会话
screen -r telegram_bot

# 查看所有会话
screen -ls
```

## 🔍 常用管理命令

### Supervisor 方式
```bash
# 启动
supervisorctl start telegram_bot

# 停止
supervisorctl stop telegram_bot

# 重启
supervisorctl restart telegram_bot

# 查看状态
supervisorctl status telegram_bot

# 查看日志
supervisorctl tail -f telegram_bot
```

### systemd 方式
```bash
# 启动
systemctl start telegram-bot

# 停止
systemctl stop telegram-bot

# 重启
systemctl restart telegram-bot

# 查看状态
systemctl status telegram-bot

# 查看日志
journalctl -u telegram-bot -n 100 -f
```

## 📊 监控和日志

### 查看运行日志
```bash
# 查看机器人日志
tail -f /www/wwwroot/telegram_bot/bot.log

# 查看最近100行
tail -n 100 /www/wwwroot/telegram_bot/bot.log

# 实时查看错误
tail -f /www/wwwroot/telegram_bot/bot.log | grep ERROR
```

### 在宝塔面板中查看
1. 进入 **文件管理**
2. 导航到 `/www/wwwroot/telegram_bot/`
3. 右键点击 `bot.log` → **编辑** 或 **查看**

## 🔒 安全配置

### 1. 配置防火墙

```bash
# 查看防火墙状态
firewall-cmd --state

# 如果需要开放端口（通常机器人不需要）
# firewall-cmd --permanent --add-port=8080/tcp
# firewall-cmd --reload
```

### 2. 设置文件权限

```bash
# 设置目录权限
chown -R www:www /www/wwwroot/telegram_bot
chmod -R 755 /www/wwwroot/telegram_bot

# 保护配置文件
chmod 600 /www/wwwroot/telegram_bot/.env

# 保护数据库文件
chmod 600 /www/wwwroot/telegram_bot/telegram_bot.db
```

### 3. 配置 SELinux（如果启用）

```bash
# 检查 SELinux 状态
getenforce

# 如果是 Enforcing，可能需要设置权限
semanage fcontext -a -t httpd_sys_rw_content_t "/www/wwwroot/telegram_bot(/.*)?"
restorecon -Rv /www/wwwroot/telegram_bot
```

## 🔄 更新和维护

### 更新代码
```bash
cd /www/wwwroot/telegram_bot

# 备份数据库
cp telegram_bot.db telegram_bot.db.backup.$(date +%Y%m%d)

# 更新代码
git pull  # 如果使用 git

# 或者手动上传新的 sxbot.py

# 重启服务
supervisorctl restart telegram_bot
# 或
systemctl restart telegram-bot
```

### 备份数据
```bash
# 创建备份目录
mkdir -p /www/backup/telegram_bot

# 备份数据库
cp /www/wwwroot/telegram_bot/telegram_bot.db /www/backup/telegram_bot/telegram_bot.db.$(date +%Y%m%d)

# 备份配置
cp /www/wwwroot/telegram_bot/.env /www/backup/telegram_bot/.env.$(date +%Y%m%d)

# 或使用宝塔面板的计划任务自动备份
```

在宝塔面板中设置自动备份：
1. 进入 **计划任务**
2. 添加 **Shell脚本** 任务
3. 执行周期：每天
4. 脚本内容：
```bash
#!/bin/bash
cd /www/wwwroot/telegram_bot
cp telegram_bot.db /www/backup/telegram_bot/telegram_bot.db.$(date +%Y%m%d)
# 删除30天前的备份
find /www/backup/telegram_bot/ -name "*.db.*" -mtime +30 -delete
```

## 🐛 故障排查

### 1. 机器人无法启动

检查日志：
```bash
tail -n 50 /www/wwwroot/telegram_bot/bot.log
```

常见问题：
- 检查 `.env` 配置是否正确
- 检查 Python 版本是否正确
- 检查依赖是否安装完整：`pip list`

### 2. 权限错误

```bash
# 重新设置权限
chown -R www:www /www/wwwroot/telegram_bot
chmod -R 755 /www/wwwroot/telegram_bot
```

### 3. 数据库锁定

```bash
# 检查是否有其他进程使用数据库
lsof /www/wwwroot/telegram_bot/telegram_bot.db

# 如果有，停止相关进程
supervisorctl stop telegram_bot
```

### 4. 内存不足

```bash
# 查看内存使用
free -h

# 查看进程内存
ps aux | grep python

# 如果内存不足，考虑添加 swap
dd if=/dev/zero of=/swapfile bs=1M count=2048
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 📞 技术支持

如遇问题，请检查：
1. 系统日志：`/www/wwwroot/telegram_bot/bot.log`
2. Supervisor日志：`/www/wwwroot/telegram_bot/supervisor.log`
3. 系统日志：`journalctl -xe`

## ✅ 部署检查清单

- [ ] Python 3.8+ 已安装
- [ ] 虚拟环境已创建
- [ ] 依赖包已安装
- [ ] .env 配置文件已正确配置
- [ ] 文件权限已正确设置
- [ ] Supervisor/systemd 服务已配置
- [ ] 机器人已成功启动
- [ ] 可以在 Telegram 中访问机器人
- [ ] 日志正常输出
- [ ] 备份计划已设置

---

**完成以上步骤后，您的 Telegram 机器人就可以在宝塔面板上稳定运行了！**
