# pgyer-ipa-extract

**English** | [简体中文](#简体中文)

Extract iOS IPA packages from [pgyer.com](https://www.pgyer.com) short links — no login, no iOS device, no API key required.

---

## English

### What it does

Given a pgyer short link (e.g. `https://www.pgyer.com/AbCd`), the script:

1. Solves the Alibaba Cloud `acw_sc__v2` JavaScript challenge
2. Parses `aKey` / `installToken` from the app page
3. Follows the `/app/install/<aKey>` → `itms-services://` redirect
4. Fetches the OTA manifest (plist) using the client UA that the endpoint whitelists
5. Downloads the signed `oss.pgyer.com` URL and verifies the package

Works purely over HTTP. Only the public distribution flow is used.

### Requirements

- Python 3.8+
- [`requests`](https://pypi.org/project/requests/) — `pip install requests`

### Install

```bash
git clone https://github.com/xuanyiran/pgyer-ipa-extract.git
cd pgyer-ipa-extract
pip install requests
```

As a **ZCode skill**: copy the folder to `~/.zcode/skills/pgyer-ipa-extract/` (Windows: `%USERPROFILE%\.zcode\skills\pgyer-ipa-extract\`). It can then be triggered by description or invoked as `/pgyer-ipa-extract`.

### Usage

```bash
# Resolve the download URL only (fast, no download)
python scripts/pgyer_ipa.py "https://www.pgyer.com/AbCd" --no-download

# Full download + integrity verification
python scripts/pgyer_ipa.py "https://www.pgyer.com/AbCd" -o ./dl

# Bare short code and 32-hex app key are also accepted
python scripts/pgyer_ipa.py AbCd -o ./dl
```

| Flag | Description |
|---|---|
| `-o, --outdir` | Output directory (default: `./pgyer_downloads`) |
| `--no-download` | Resolve the direct URL only |
| `--acw-key` | Override the `acw_sc__v2` XOR key (default: standard value) |

The output file is named from the `Content-Disposition` header (e.g. `AppName_1.2.3.ipa`), and the script prints the bundle identifier, version and minimum iOS from the embedded `Info.plist`.

### How it works

| Step | Detail |
|---|---|
| 1. Challenge | The short link returns a gzip'd `acw_sc__v2` challenge page. `arg1` is permuted with a fixed table and XORed with a fixed key, producing the cookie value. |
| 2. Page parse | Inline JS variables expose `aType`, `aKey`, `installToken`, `timeSign`, `lang`. |
| 3. Install URL | `GET /app/install/<aKey>?time=...&lang=cn&installToken=...` → `302 itms-services://...url=<plist>` |
| 4. Plist URL | Usually `/app/plist/<aKey>/install//s.plist?` — the empty path segment is normal. |
| 5. Plist fetch | **Must** use `User-Agent: com.apple.appstored/1.0`; browser UAs get 404. |
| 6. Direct URL | `assets[kind=software-package].url` is the signed `oss.pgyer.com` link. |
| 7. Verify | `zipfile` integrity check + `Payload/*.app/Info.plist`. |

### Troubleshooting

- **Page is ~2.7 KB of obfuscated JS** — the challenge page is gzip-compressed; add `--compressed` to curl (requests handles it automatically).
- **`InvalidSchema: ... itms-services://`** — do not follow the redirect; read `Location` with `allow_redirects=False`.
- **plist returns 404 for every path** — it is UA-gated; use `com.apple.appstored/1.0`.
- **Direct URL returns 403** — the `auth_key` signature expires within hours; re-run the install step to mint a fresh URL.
- **Windows console `UnicodeEncodeError`** — the script forces UTF-8 output internally.

### Scope

- iOS only (`aType=ios`). Android packages use a different flow.
- Different short links may point to white-label builds of the same bundle; always trust the package's own `Info.plist` over the page title.

### Disclaimer

This tool is intended for downloading publicly distributed builds or packages you are authorized to test. Respect the platform's terms of service and applicable law.

### License

[MIT](LICENSE)

---

## 简体中文

### 功能简介

给定蒲公英短链（如 `https://www.pgyer.com/AbCd`），脚本会：

1. 通过阿里云盾 `acw_sc__v2` JS 挑战
2. 从应用页解析 `aKey` / `installToken`
3. 请求 `/app/install/<aKey>`，拿到 `itms-services://` 跳转
4. 用接口白名单要求的 UA 拉取 OTA 清单（plist）
5. 从 `oss.pgyer.com` 签名直链下载并校验安装包

全程纯 HTTP，走的是公开分发流程，不需要登录、不需要 iOS 设备、不需要 pgyer API key。

### 环境要求

- Python 3.8+
- [`requests`](https://pypi.org/project/requests/)：`pip install requests`

### 安装

```bash
git clone https://github.com/xuanyiran/pgyer-ipa-extract.git
cd pgyer-ipa-extract
pip install requests
```

作为 **ZCode 技能**：把整个目录拷到 `~/.zcode/skills/pgyer-ipa-extract/`（Windows：`%USERPROFILE%\.zcode\skills\pgyer-ipa-extract\`），之后可被描述自动触发，或直接用 `/pgyer-ipa-extract` 调用。

### 用法

```bash
# 只解析直链，不下载（秒出，适合先验证链路）
python scripts/pgyer_ipa.py "https://www.pgyer.com/AbCd" --no-download

# 完整下载 + 完整性校验
python scripts/pgyer_ipa.py "https://www.pgyer.com/AbCd" -o ./dl

# 也接受裸短码和 32 位 appKey
python scripts/pgyer_ipa.py AbCd -o ./dl
```

| 参数 | 说明 |
|---|---|
| `-o, --outdir` | 输出目录（默认 `./pgyer_downloads`） |
| `--no-download` | 只解析直链 |
| `--acw-key` | 覆盖 `acw_sc__v2` 异或 key（默认标准值） |

输出文件名取自 OSS 的 `Content-Disposition`（如 `应用名_1.2.3.ipa`），脚本还会打印包内 `Info.plist` 的 bundle id、版本号和最低 iOS 版本。

### 原理

| 步骤 | 说明 |
|---|---|
| 1. 过盾 | 短链返回 gzip 压缩的 `acw_sc__v2` 挑战页；`arg1` 按固定置换表重排后与固定 key 十六进制异或，得到 cookie |
| 2. 解析页面 | 内联 JS 变量里有 `aType`、`aKey`、`installToken`、`timeSign`、`lang` |
| 3. 安装接口 | `GET /app/install/<aKey>?time=...&lang=cn&installToken=...` → `302 itms-services://...url=<plist>` |
| 4. plist 路径 | 形如 `/app/plist/<aKey>/install//s.plist?`，双斜杠是正常的空段 |
| 5. 拉取 plist | **必须**用 `User-Agent: com.apple.appstored/1.0`，浏览器 UA 一律 404 |
| 6. 直链 | plist 中 `assets[kind=software-package].url` 即 `oss.pgyer.com` 签名直链 |
| 7. 校验 | `zipfile` 完整性校验 + 读取 `Payload/*.app/Info.plist` |

### 常见问题

- **页面只有 2.7KB 混淆 JS**：挑战页是 gzip 的，curl 加 `--compressed`（requests 会自动解压）
- **报 `InvalidSchema: ... itms-services://`**：不要跟随跳转，用 `allow_redirects=False` 读 `Location`
- **plist 换任何路径都 404**：是 UA 白名单，必须用 `com.apple.appstored/1.0`
- **直链下载 403**：`auth_key` 几小时内过期，重新走安装接口换新直链
- **Windows 控制台 UnicodeEncodeError**：脚本内部已强制 UTF-8 输出

### 适用范围

- 仅覆盖 iOS（`aType=ios`）。Android 包的下发流程不同，不在本工具范围。
- 不同短链可能指向同一 bundle id 的白标皮肤；以包内 `Info.plist` 为准，不要只看页面标题。

### 免责声明

本工具仅用于下载公开发行的安装包，或你已获授权测试的包。请遵守平台服务条款和当地法律法规。

### 许可证

[MIT](LICENSE)
