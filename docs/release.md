# Release Flow

This repository uses [`version.json`](../version.json) as the single runtime version source.

- Python runtime reads it through [`constants.py`](../wechat_agent/constants.py)
- Node media CLI reads it through [`wechat-media-cli.mjs`](../scripts/wechat-media-cli.mjs)
- `package.json` and `package-lock.json` are synchronized by the release script

## Prepare A Release

Run:

```bash
npm run release:check -- 1.2.2
npm run release:prepare -- 1.2.2
```

This updates:

- `version.json`
- `package.json`
- `package-lock.json`

## Publish Checklist

1. Review the diff with `git diff`
2. Commit with `git commit -am "release: v1.2.2"`
3. Tag with `git tag v1.2.2`
4. Push code and tags to GitHub: `git push origin main --tags`
5. Push code and tags to Gitee: `git push gitee main --tags`
6. Create a GitHub Release for `v1.2.2`
7. Copy the same release notes to Gitee if needed

## Notes

- Keep feature merges and releases separate
- Only bump the version when you are ready to ship
- If you later publish to npm or PyPI, use the same git tag as the source of truth for the public package
