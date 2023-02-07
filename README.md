# notion2hexo
功能：notion写文章，同步到hexo博客上



配置：

```json
{
  "notion_key": "secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "blog_db_id": "888888888888888888888888888888888",
  "local_dir": "./hexo",
  "oss_access_key_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "oss_access_key_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "oss_endpoint": "oss-cn-beijing.aliyuncs.com",
  "bucket_name": "bucket_name",
  "upload_prefix": "upload_prefix/"
}
```

- notion_key：notion访问博客数据库key
- blog_db_id：notion博客存储数据库id
- local_dir：输出博客本地目录（_post相对目录）
- OSS图床配置（阿里云）
  - oss_access_key_id
  - oss_access_key_secret
  - oss_endpoint
  - bucket_name
  - upload_prefix：上传目录
