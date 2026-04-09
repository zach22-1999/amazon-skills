# Release Gate

这个仓库在本机默认受发布前审计脚本保护。

## 推送前固定步骤

1. 先在私人工作区完成修改
2. 同步到当前公开工作区
3. 运行：

```bash
python3 ../_templates/scripts/release_audit.py --repo "$(pwd)"
```

4. 只有结果不是 `BLOCKED` 时，才允许继续推送

如果你直接执行 `git push`，本机 `pre-push` hook 也会自动运行同一套审计。
