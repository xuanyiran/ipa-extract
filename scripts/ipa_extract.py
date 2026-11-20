#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ipa-extract: 从分发平台短链提取 iOS IPA（当前仅实现蒲公英 pgyer.com）。

用法:
    python ipa_extract.py https://www.pgyer.com/AbCd -o ./dl
    python ipa_extract.py AbCd --no-download        # 只解析直链

依赖: requests (pip install requests)
"""
import argparse
import os
import plistlib
import re
import sys
import time
import urllib.parse
import zipfile

import requests

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

POS = [0xf, 0x23, 0x1d, 0x18, 0x21, 0x10, 0x1, 0x26, 0xa, 0x9, 0x13, 0x1f, 0x28,
       0x1b, 0x16, 0x17, 0x19, 0xd, 0x6, 0xb, 0x27, 0x12, 0x14, 0x8, 0xe, 0x15,
       0x20, 0x1a, 0x2, 0x1e, 0x7, 0x4, 0x11, 0x5, 0x3, 0x1c, 0x22, 0x25, 0xc, 0x24]
DEFAULT_ACW_KEY = '3000176000856006061501533003690027800375'
IOS_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
          'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
          'Mobile/15E148 Safari/604.1')
APPSTORED_UA = 'com.apple.appstored/1.0'   # plist 端点只放行这个 UA


def log(*args):
    print('[pgyer]', *args, flush=True)


# ---------- acw_sc__v2 ----------

def unsbox(arg1):
    out = [''] * len(POS)
    for i, ch in enumerate(arg1):
        for j, p in enumerate(POS):
            if p == i + 1:
                out[j] = ch
    return ''.join(out)


def hex_xor(a, b):
    r = ''
    for i in range(0, len(a), 2):
        if i < len(b):
            r += '%02x' % (int(a[i:i + 2], 16) ^ int(b[i:i + 2], 16))
    return r


def acw_cookie(arg1, key):
    return hex_xor(unsbox(arg1), key)


class Pgyer:
    def __init__(self, acw_key=DEFAULT_ACW_KEY):
        self.s = requests.Session()
        self.s.headers.update({
            'User-Agent': IOS_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        self.acw_key = acw_key

    def get(self, url, **kw):
        kw.setdefault('timeout', 30)
        r = self.s.get(url, **kw)
        ctype = r.headers.get('content-type') or ''
        if 'text/html' in ctype and "arg1='" in r.text[:8000]:
            m = re.search(r"arg1='([0-9A-Fa-f]+)'", r.text[:8000])
            if m:
                ck = acw_cookie(m.group(1), self.acw_key)
                log('命中 acw_sc__v2 挑战，cookie =', ck)
                self.s.cookies.set('acw_sc__v2', ck, domain='www.pgyer.com')
                r = self.s.get(url, **kw)
        return r


# ---------- 页面解析 ----------

def page_vars(html):
    def g(name):
        m = re.search(r'\b' + name + r"\s*=\s*(?:'([^']*)'|\"([^\"]*)\")", html)
        if not m:
            return None
        return m.group(1) if m.group(1) is not None else m.group(2)

    return {k: g(k) for k in
            ('aType', 'aKey', 'aVersion', 'installToken', 'timeSign', 'lang')}


def decode_time_sign(v):
    if v and len(v) % 2 == 0 and re.fullmatch(r'[0-9A-Fa-f]+', v):
        try:
            return bytes.fromhex(v).decode('ascii')
        except UnicodeDecodeError:
            pass
    return v or ''


def get_plist_url(pg, origin, page):
    akey = page['aKey']
    q = {'time': int(time.time() * 1000), 'lang': page.get('lang') or 'cn'}
    if page.get('installToken'):
        q['installToken'] = page['installToken']
    ts = decode_time_sign(page.get('timeSign'))
    if ts:
        q['timeSign'] = ts
    url = origin + '/app/install/' + akey + '?' + urllib.parse.urlencode(q)
    r = pg.get(url, allow_redirects=False)
    loc = r.headers.get('Location', '')
    if not loc.startswith('itms-services://'):
        m = re.search(r"itms-services://[^\"'<>\s]+", r.text or '')
        if m:
            loc = m.group(0)
    if not loc.startswith('itms-services://'):
        raise SystemExit('未获得 itms-services 跳转: status=%s body=%r'
                         % (r.status_code, (r.text or '')[:300]))
    qs = urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query)
    pu = qs.get('url', [None])[0]
    if not pu:
        raise SystemExit('itms-services 中无 url 参数: ' + loc)
    return pu


def fetch_plist(plist_url):
    r = requests.get(plist_url, headers={'User-Agent': APPSTORED_UA}, timeout=60)
    if r.status_code != 200 or b'plist' not in r.content[:400]:
        raise SystemExit(
            'plist 获取失败: status=%s len=%s\n'
            '提示: plist 端点只认 User-Agent: com.apple.appstored/1.0'
            % (r.status_code, len(r.content)))
    data = plistlib.loads(r.content)
    item = data['items'][0]
    meta = item.get('metadata', {})
    asset = next(a for a in item['assets']
                 if a.get('kind') == 'software-package')
    return asset['url'], meta


# ---------- 下载与校验 ----------

def sanitize_filename(name, fallback='app.ipa'):
    name = (name or '').replace('\\', '_').replace('/', '_').strip()
    name = re.sub(r'[\x00-\x1f<>:"|?*]', '_', name)
    return name or fallback


def download(url, outdir, meta):
    os.makedirs(outdir, exist_ok=True)
    with requests.get(url, headers={'User-Agent': APPSTORED_UA},
                      stream=True, timeout=120) as r:
        r.raise_for_status()
        fn = None
        cd = r.headers.get('Content-Disposition') or ''
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd, re.I)
        if m:
            fn = urllib.parse.unquote(m.group(1).strip().strip('"'))
        if not fn:
            fn = '%s_%s.ipa' % (meta.get('title') or 'app',
                                meta.get('bundle-version') or 'unknown')
        path = os.path.join(outdir, sanitize_filename(fn))
        total = int(r.headers.get('Content-Length') or 0)
        done = 0
        last_pct = -1
        t0 = time.time()
        with open(path, 'wb') as f:
            for chunk in r.iter_content(1 << 20):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    if pct // 10 != last_pct // 10:
                        last_pct = pct
                        log('下载 %d%% (%.1f/%.1f MB)' %
                            (pct, done / 1048576, total / 1048576))
        log('下载完成: %s (%.1f MB, %.1fs)' %
            (path, done / 1048576, time.time() - t0))
    return path


def verify(path):
    if not zipfile.is_zipfile(path):
        raise SystemExit('不是有效 zip/ipa: ' + path)
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        infos = [n for n in z.namelist()
                 if re.match(r'Payload/[^/]+\.app/Info\.plist$', n)]
        d = plistlib.loads(z.read(infos[0])) if infos else {}
    log('zip 校验:', 'OK' if bad is None else '损坏 @ ' + str(bad))
    for k in ('CFBundleIdentifier', 'CFBundleShortVersionString',
              'CFBundleVersion', 'MinimumOSVersion'):
        if d.get(k):
            log('  %s = %s' % (k, d[k]))
    return d


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description='从蒲公英(pgyer.com)短链提取 iOS IPA')
    ap.add_argument('target', help='短链 URL、短码（如 AbCd）或 32 位 appKey')
    ap.add_argument('-o', '--outdir', default='pgyer_downloads',
                    help='输出目录（默认 ./pgyer_downloads）')
    ap.add_argument('--no-download', action='store_true',
                    help='只解析出直链，不下载')
    ap.add_argument('--acw-key', default=DEFAULT_ACW_KEY,
                    help='acw_sc__v2 异或 key（默认标准值）')
    args = ap.parse_args()

    t = args.target.strip()
    page_url = t if t.startswith('http') else 'https://www.pgyer.com/' + t

    pg = Pgyer(args.acw_key)
    log('页面:', page_url)
    r = pg.get(page_url)
    if r.status_code != 200:
        raise SystemExit('页面获取失败: HTTP %s' % r.status_code)

    page = page_vars(r.text)
    log('aType=%s aKey=%s aVersion=%s' %
        (page.get('aType'), page.get('aKey'), page.get('aVersion')))
    if not page.get('aKey'):
        raise SystemExit('页面里没找到 aKey（短链无效或应用已删除）')
    if page.get('aType') and page.get('aType') != 'ios':
        raise SystemExit('该包不是 iOS (aType=%s)，本技能只处理 iOS'
                         % page['aType'])

    origin = '{0.scheme}://{0.netloc}'.format(urllib.parse.urlsplit(r.url))
    plist_url = get_plist_url(pg, origin, page)
    log('plist:', plist_url)

    ipa_url, meta = fetch_plist(plist_url)
    log('bundle: %s  version: %s' %
        (meta.get('bundle-identifier'), meta.get('bundle-version')))
    log('IPA 直链:', ipa_url)

    if args.no_download:
        return
    verify(download(ipa_url, args.outdir, meta))


if __name__ == '__main__':
    main()
