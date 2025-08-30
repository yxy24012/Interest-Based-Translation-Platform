# 翻译平台

这是一个基于兴趣的翻译平台，支持多语言翻译和社区互动。

## 功能特性

### 用户角色
- **普通用户**: 可以浏览作品、评论、点赞
- **翻译者**: 可以翻译作品
- **校正者**: 可以对翻译进行校正和评论
- **管理员**: 可以管理用户和内容

### 校正者功能（新增）

校正者是一个重要的角色，负责提升翻译质量：

#### 校正者权限
- 对翻译者的翻译内容进行校正和改进
- 提供校正说明和注解
- 其他用户可以对校正内容进行点赞
- 校正者本人或管理员可以删除校正

#### 校正者申请
- 用户可以在个人资料页面申请成为校正者
- 申请后立即获得校正者权限
- 校正者需要遵守社区规则，提供建设性反馈

#### 校正功能
- 在作品详情页面，校正者可以看到"添加校正"按钮
- 校正内容包括校正文本和说明
- 其他用户可以对校正进行点赞
- 校正列表按时间倒序显示

## 安装和运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 运行应用：
```bash
python app.py
```

3. 访问 http://localhost:5000

### 邮件通知（可选）

设置环境变量以启用"收到消息自动邮件通知"功能：

```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_smtp_user
SMTP_PASS=your_smtp_password
SMTP_USE_TLS=true
FROM_EMAIL=noreply@example.com
FROM_NAME=Translation Platform
```

配置完成后，用户在个人资料中绑定邮箱，收到站内消息或系统通知时会自动发送邮件提醒。

#### 测试邮件功能

1. 配置环境变量（参考 `env_example.txt`）
2. 运行测试脚本：
```bash
python test_email.py
```
3. 按提示输入测试邮箱地址
4. 检查邮箱是否收到测试邮件

#### 常见邮箱配置

**Gmail:**
- 需要开启"两步验证"并生成"应用专用密码"
- SMTP_HOST=smtp.gmail.com
- SMTP_PORT=587

**QQ邮箱:**
- 需要在设置中开启SMTP服务并获取授权码
- SMTP_HOST=smtp.qq.com
- SMTP_PORT=587

**163邮箱:**
- 需要在设置中开启SMTP服务并获取授权码
- SMTP_HOST=smtp.163.com
- SMTP_PORT=587

## 默认账号

- 管理员: admin / admin
- 其他用户需要注册

## 技术栈

- Flask
- SQLAlchemy
- Bootstrap
- JavaScript

## 数据库模型

### 新增模型

#### Correction（校正）
- `id`: 主键
- `translation_id`: 关联的翻译ID
- `reviewer_id`: 校正者ID
- `content`: 校正内容
- `notes`: 校正说明
- `created_at`: 创建时间
- `updated_at`: 更新时间

#### CorrectionLike（校正点赞）
- `id`: 主键
- `user_id`: 用户ID
- `correction_id`: 校正ID
- `created_at`: 创建时间

## API接口

### 校正相关接口

- `POST /work/<work_id>/add_correction`: 添加校正
- `POST /work/<work_id>/delete_correction/<correction_id>`: 删除校正
- `POST /correction/<correction_id>/like`: 校正点赞
- `GET /correction/<correction_id>/likes_count`: 获取校正点赞数

## 使用说明

1. **成为校正者**：
   - 登录后进入个人资料页面
   - 点击"申请成为校正者"
   - 确认申请即可获得校正者权限

2. **进行校正**：
   - 在有翻译的作品详情页面
   - 点击"添加校正"按钮
   - 填写校正内容和说明
   - 提交校正

3. **点赞校正**：
   - 在校正列表中找到感兴趣的校正
   - 点击点赞按钮进行点赞
   - 可以取消点赞

## 注意事项

- 校正者需要提供准确和有用的校正
- 尊重翻译者的努力
- 遵守社区规则
- 管理员可以删除不当的校正 