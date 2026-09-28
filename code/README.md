# 开奖数据工作台（GUI 原型）

## 运行

```bash
uv venv
uv pip install -r requirements.txt
uv run python main.py
```

点击“导入登录态”粘贴目标网站 Local Storage 的 `user` JSON；点击“如何获取登录态”查看指引。
登录态保存于当前用户目录 `.lottery-sheet-workflow/auth.json`，文件权限限制为仅当前用户可读写；界面和错误信息不显示完整 token。
