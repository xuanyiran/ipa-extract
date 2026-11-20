---
name: pgyer-ipa-extract
description: 蒲公英 pgyer.com 免登录提取 iOS IPA 安装包。给定蒲公英短链（形如 https://www.pgyer.com/AbCd）或短码，自动过阿里云盾 acw_sc__v2 挑战、解析 aKey/installToken、走 /app/install 的 itms-services 跳转、用 com.apple.appstored UA 拉 OTA plist、再从 oss.pgyer.com 签名直链下载 IPA。当用户要求「提取/下载蒲公英上的 IPA」「pgyer 下包」，或调试中遇到 acw_sc__v2 挑战页、itms-services 302、/app/plist/.../s.plist 一律 404 时使用。
---

# pgyer-ipa-extract — 蒲公英 iOS IPA 提取

直接从蒲公英（pgyer.com）短链提取 iOS 安装包（IPA）：全程纯 HTTP，**不需要 iOS 设备、不需要登录、不需要 pgyer 开放平台 API key**。

> 仅用于公开分发或已授权的包下载与测试。

## 依赖

- Python 3.8+，`requests`（`pip install requests`）

## 快速用法

```bash
# 只解析不下包（快速验证链路，几秒）
python scripts/pgyer_ipa.py "https://www.pgyer.com/AbCd" --no-download -o ./dl

# 完整下载 + 校验
python scripts/pgyer_ipa.py "https://www.pgyer.com/AbCd" -o ./dl
```

- `target` 支持：完整短链 URL、裸短码（如 `AbCd`）、32 位 appKey
- 输出：`<outdir>/<应用名>_<版本>.ipa`（文件名取自 OSS 的 Content-Disposition），并打印 bundle id / 版本 / zip 完整性校验结果
- `--acw-key` 可覆盖 acw_sc__v2 的异或 key（见下）

## 流程（脚本内部步骤）

1. GET 短链 → 命中阿里云盾 `acw_sc__v2` 挑战页：JS 里 `arg1='...'`，用固定置换表 unsbox 后与固定 key 异或 → 设 cookie 重放
2. 解析页面内联变量：`aType='ios'`、`aKey`（=buildKey）、`installToken`、`timeSign`、`lang`
3. GET `/app/install/<aKey>?time=<ms>&lang=cn&installToken=...&timeSign=...` → 302 到 `itms-services://?action=download-manifest&url=<plist>`
4. 从 Location 里解析 plist URL（形如 `/app/plist/<aKey>/install//s.plist?`，**双斜杠是正常的空段**）
5. **用 `User-Agent: com.apple.appstored/1.0`** GET plist —— 浏览器/普通 UA 一律 404，这是最关键的一步
6. plist 中 `assets[kind=software-package].url` 即 `https://oss.pgyer.com/<hash>.ipa?auth_key=...` 签名直链
7. 下载、zip 完整性校验、读 `Payload/*.app/Info.plist` 打印真实身份

## 关键坑（均实测踩过）

| 现象 | 原因 / 解法 |
|---|---|
| 页面只有 2.7KB，解压后是混淆 JS | 短链返回 gzip 压缩的挑战页；curl 要加 `--compressed`，requests 自动解压 |
| 页面含 `arg1='...'` | 阿里云盾 acw_sc__v2；算法见下，标准 key 为 `3000176000856006061501533003690027800375` |
| requests 跟跳转报 `InvalidSchema: No connection adapters for 'itms-services://...'` | 302 目标是 `itms-services://`；必须 `allow_redirects=False` 读 `Location`，不能自动跟随 |
| `/app/plist/.../s.plist` 换任何路径组合都 404 | **UA 白名单**：plist 端点只放行 `com.apple.appstored/1.0`（iOS OTA 客户端 UA） |
| 直链下载 403 / auth_key 过期 | `auth_key` 有时效（小时级），重新走第 3 步换新直链再下 |
| `/install//s.plist` 双斜杠 | 正常，空段不要"修正" |
| Windows 控制台中文报 UnicodeEncodeError | 脚本已 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` |

### acw_sc__v2 算法

```python
POS = [0xf,0x23,0x1d,0x18,0x21,0x10,0x1,0x26,0xa,0x9,0x13,0x1f,0x28,0x1b,0x16,0x17,
       0x19,0xd,0x6,0xb,0x27,0x12,0x14,0x8,0xe,0x15,0x20,0x1a,0x2,0x1e,0x7,0x4,
       0x11,0x5,0x3,0x1c,0x22,0x25,0xc,0x24]
KEY = '3000176000856006061501533003690027800375'
```

1. unsbox：按 POS 表重排 `arg1` 的字符
2. 结果与 KEY 逐字节十六进制异或
3. `acw_sc__v2=<结果>` 写入 cookie（domain=www.pgyer.com）后重放原 URL

若平台更换 key（设了 cookie 仍是挑战页）：用真实浏览器打开页面复制 `acw_sc__v2` cookie，或从挑战脚本里反混淆出传给 hexXor 的第二个参数，再用 `--acw-key` 传入。

## 手动复现（无脚本）

```bash
# 1. 拿页面（--compressed 解 gzip）
curl -s --compressed -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
     https://www.pgyer.com/AbCd -o page.html
# 2. 搜 arg1='...' 按上面算法算 cookie，带 cookie 重放拿到真实页面
# 3. 页面里找 aKey = '<32hex>' 与 installToken = "<token>"
curl -si -A "<iPhone UA>" \
  "https://www.pgyer.com/app/install/<aKey>?time=$(date +%s%3N)&lang=cn&installToken=<token>" \
  | grep -i '^location'
# 4. 用 Location 里的 plist url 取 plist（注意 UA）
curl -s -A "com.apple.appstored/1.0" "https://www.pgyer.com/app/plist/<aKey>/install//s.plist?"
# 5. 从 plist 的 software-package url 下载
curl -L -A "com.apple.appstored/1.0" -o app.ipa "<oss url>"
```

## 输出校验

```bash
unzip -t app.ipa            # zip 完整性
unzip -l app.ipa | head     # 应见 Payload/<Name>.app/...
```

脚本会自动读 `Payload/*.app/Info.plist`，打印 `CFBundleIdentifier / CFBundleShortVersionString / CFBundleVersion / MinimumOSVersion`。

## 范围与注意

- 仅覆盖 **iOS（aType=ios）**。Android 包（aType=android）的下发路径不同，不在本技能范围。
- **白标包**：不同短链可能指向同一 bundle id 的不同皮肤（显示名不同、可执行文件相同），以包内 Info.plist 为准，不要只看页面标题。
- plist 的 metadata 由发布方填写，bundle-identifier 可能与实际包不一致，最终以包内 Info.plist 为准。
