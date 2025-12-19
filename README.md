# 极简视频托管网站

基于 Flask + Cloudflare R2 的极简视频托管平台。

## 功能特性

- 视频上传和管理
- 视频封面支持
- 管理员后台
- 全屏播放支持
- 使用 Cloudflare R2 对象存储

## 部署说明

请参考 `部署教程.md` 文件，按照步骤部署到 Render + Cloudflare R2。

## 技术栈

- Python 3.11+
- Flask
- Gunicorn
- Boto3 (AWS SDK for Python)
- Cloudflare R2
- Tailwind CSS

## 环境变量

部署时需要配置以下环境变量：

- `SECRET_KEY`: Flask 会话密钥
- `ADMIN_PASSWORD`: 管理员密码
- `R2_ACCESS_KEY_ID`: R2 访问密钥 ID
- `R2_SECRET_ACCESS_KEY`: R2 秘密访问密钥
- `R2_ENDPOINT_URL`: R2 API 地址
- `R2_BUCKET_NAME`: R2 存储桶名称
- `R2_PUBLIC_URL`: R2 公共访问地址
