# -*- coding: utf-8 -*-
"""
TVBox 图片站源 - 公子留步 (www.gzlb.net)
- 列表：<a class="f_item"> 卡片（懒加载 _src）
- 详情：单集"在线观看$详情URL"
- 播放：详情页 + _N.html 全部分页 → pics:// 拼接
"""

import sys
import re
import json
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append('..')

try:
    import requests
except ImportError:
    requests = None

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def homeContent(self, filter): pass
        def categoryContent(self, tid, pg, filter, extend): pass
        def detailContent(self, ids): pass
        def searchContent(self, key, quick): pass
        def playerContent(self, flag, id, vipFlags): pass


HOST = "https://www.gzlb.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

CATS = [
    ("1",  "人体艺术", "rentiyishu"),
    ("2",  "美女写真", "meinvxiezhen"),
    ("3",  "性感美女", "xingganmeinv"),
    ("4",  "丝袜美腿", "siwameitui"),
    ("5",  "清纯可爱", "qingchunkeai"),
    ("6",  "明星壁纸", "mingxing"),
    ("7",  "模特写真", "mote"),
    ("8",  "美女车模", "chemo"),
    ("9",  "街拍美女", "jiepaimeinv"),
    ("10", "最新图片", "zuixin"),
    ("11", "网络美媚", "wangluomeinv"),
    ("12", "制服诱惑", "zhifuyouhuo"),
    ("13", "古装美女", "guzhuangmeinv"),
    ("14", "气质佳丽", "qizhimeinv"),
    ("15", "Cosplay", "cosplay"),
    ("16", "美女头像", "meinvtouxiang"),
    ("17", "欧美美女", "oumeimeinv"),
]
CAT_DIR = {c[0]: c[2] for c in CATS}

# 分类分页 URL 模式缓存：{cat_slug: "https://.../page/{N}.html"}
_CAT_PAGE_PATTERN = {}


# ---------------------------------------------------------------- 基础
def _get(url, referer=None, timeout=20):
    if not url:
        return ""
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer or (HOST + "/"),
    }
    try:
        if requests:
            r = requests.get(url, headers=headers, timeout=timeout)
            return r.content.decode("utf-8", errors="ignore")
        else:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[GET ERR] {url} -> {e}")
        return ""


def _fix(u):
    if not u:
        return ""
    u = u.strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return HOST + u
    if not u.startswith("http"):
        return HOST + "/" + u.lstrip("/")
    return u


def _parse_id_from_url(url):
    m = re.search(r'/([A-Za-z0-9_\-]+)/(\d+)\.html', url or '')
    if m:
        return m.group(1), m.group(2)
    return None, None


def _is_list_thumb(u):
    """列表缩略图 / 焦点图 / UI 图，不算详情大图"""
    low = (u or "").lower()
    if '/focus/' in low:
        return True
    if re.search(r'/list\d+/', low):
        return True
    for kw in ('/style/', '/js/', 'lazy', 'blank', 'logo', 'icon', 'btn', 'avatar'):
        if kw in low:
            return True
    return False


# ---------------------------------------------------------------- 列表解析
def parse_list(html):
    result = []
    if not html:
        return result

    # 优先 f_item 卡片
    for item in re.findall(r'<a\b[^>]*class="[^"]*\bf_item\b[^"]*"[^>]*>.*?</a>',
                           html, re.S):
        hm = re.search(r'href="([^"]+)"', item)
        if not hm:
            continue
        href = _fix(hm.group(1))

        pm = re.search(r'_src="([^"]+)"', item)
        if not pm:
            pm = re.search(r'<img[^>]+src="([^"]+)"', item)
        pic = _fix(pm.group(1)) if pm else ""
        if pic and ('lazy' in pic.lower() or 'blank' in pic.lower()):
            pm2 = re.search(r'_src="([^"]+)"', item)
            pic = _fix(pm2.group(1)) if pm2 else ""

        tm = re.search(r'<h4[^>]*>([^<]+)</h4>', item)
        if not tm:
            tm = re.search(r'alt="([^"]*)"', item)
        name = tm.group(1).strip() if tm else ""

        if name and href:
            result.append({
                "vod_id": href,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": "",
                "vod_play_from": "图集",
            })

    # 兼容 AJAX 片段返回的纯卡片（同上正则即可覆盖）
    return result


# ---------------------------------------------------------------- 分类页翻页
def _fetch_cat_page(cat, pg):
    """获取分类页第 pg 页，自动探测分页模式并缓存"""
    if pg <= 1:
        return _get(f"{HOST}/{cat}/", referer=HOST + "/")

    # 已缓存模式
    pattern = _CAT_PAGE_PATTERN.get(cat)
    if pattern:
        url = pattern.replace("{N}", str(pg))
        html = _get(url, referer=f"{HOST}/{cat}/")
        if html and 'f_item' in html:
            return html
        # 该模式对本页失效，清缓存重探
        _CAT_PAGE_PATTERN.pop(cat, None)

    # 探测：尝试常见模式
    candidates = [
        f"{HOST}/{cat}/page/{{N}}.html",
        f"{HOST}/{cat}/page_{{N}}.html",
        f"{HOST}/{cat}/index_{{N}}.html",
        f"{HOST}/{cat}/list_{{N}}.html",
        f"{HOST}/{cat}/{{N}}.html",
        f"{HOST}/{cat}/?page={{N}}",
        f"{HOST}/{cat}/?p={{N}}",
        f"{HOST}/?cid={{cid}}&page={{N}}",  # cid 需从 HTML 里读，暂用 0
    ]
    for pat in candidates:
        test_url = pat.replace("{N}", str(pg)).replace("{cid}", "0")
        html = _get(test_url, referer=f"{HOST}/{cat}/")
        if html and 'f_item' in html:
            _CAT_PAGE_PATTERN[cat] = pat
            print(f"[pagination] {cat} -> {pat}")
            return html
    return ""


# ---------------------------------------------------------------- 详情页图片
def _extract_page_images(html):
    """从详情页 HTML 里提取大图 URL（保留原顺序，未去重）"""
    imgs = []
    if not html:
        return imgs

    # 1) 首选：pic.gzlb.net 上的详情大图（过滤 list 缩略图 / focus）
    for m in re.finditer(r'<img[^>]+src="(https?://pic\.gzlb\.net/[^"]+)"', html):
        u = m.group(1)
        if _is_list_thumb(u):
            continue
        imgs.append(u)

    # 2) 兜底：所有 http 图（过滤 UI 图）
    if not imgs:
        for m in re.finditer(r'<img[^>]+src="(https?://[^"]+)"', html):
            u = m.group(1)
            if _is_list_thumb(u):
                continue
            imgs.append(u)
    return imgs


def _collect_detail_images(detail_url, first_html):
    """并发抓取全部 _N.html 分页，按顺序合并图片"""
    images = []
    seen = set()

    def add_all(urls):
        for u in urls:
            full = _fix(u)
            if full and full not in seen:
                seen.add(full)
                images.append(full)

    add_all(_extract_page_images(first_html))

    cat, base_id = _parse_id_from_url(detail_url)
    if not (cat and base_id):
        return images

    # 总页数：(1/34)
    pm = re.search(r'[\(（]\s*(\d+)\s*/\s*(\d+)\s*[\)）]', first_html)
    if not pm:
        return images
    total = int(pm.group(2))
    if total <= 1:
        return images
    total = min(total, 500)  # 保护上限

    def fetch(page):
        url = f"{HOST}/{cat}/{base_id}_{page}.html"
        return page, _get(url, referer=detail_url, timeout=15)

    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(fetch, p) for p in range(2, total + 1)]
        for f in as_completed(futs):
            try:
                p, h = f.result()
                results[p] = h
            except Exception as e:
                print(f"[detail fetch] {e}")

    for p in range(2, total + 1):
        add_all(_extract_page_images(results.get(p) or ""))

    return images


# ---------------------------------------------------------------- Spider
class Spider(BaseSpider):
    def __init__(self): pass
    def getName(self): return "公子留步"
    def init(self, extend=""): pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|avi|mkv|ts|mov|jpg|jpeg|png|webp|gif)(\?|$)',
                              url or '', re.I))
    def manualVideoCheck(self): return False

    def homeContent(self, filter=False):
        return {
            "class": [{"type_id": c[0], "type_name": c[1]} for c in CATS],
            "filters": {}
        }

    def homeVideoContent(self):
        try:
            html = _get(HOST + "/")
            return {"list": parse_list(html)}
        except Exception as e:
            print(f"[homeVideoContent] {e}")
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        cat = CAT_DIR.get(str(tid))
        if not cat:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 0, "total": 0}
        try:
            html = _fetch_cat_page(cat, pg)
            videos = parse_list(html)
            if videos:
                # pagecount = pg + 1，让 TVBox 允许继续下滑加载
                return {"list": videos, "page": pg, "pagecount": pg + 1,
                        "limit": len(videos), "total": -1}
            else:
                return {"list": [], "page": pg, "pagecount": pg,
                        "limit": 0, "total": 0}
        except Exception as e:
            print(f"[categoryContent] {e}")
            return {"list": [], "page": pg, "pagecount": pg, "limit": 0, "total": 0}

    def searchContent(self, key, quick=False):
        try:
            if not key:
                return {"list": []}
            from urllib.parse import quote
            url = f"{HOST}/search/?q={quote(key)}"
            html = _get(url, referer=HOST + "/")
            return {"list": parse_list(html)}
        except Exception as e:
            print(f"[searchContent] {e}")
            return {"list": []}

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid:
            return {"list": []}
        if not vid.startswith("http"):
            vid = _fix(vid)
        html = _get(vid, referer=HOST + "/")
        if not html:
            return {"list": []}

        title = ""
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if m:
            title = m.group(1).strip()
        if not title:
            m = re.search(r'<title>([^<]+)</title>', html)
            if m:
                title = m.group(1).split("-")[0].strip()

        if any(k in (title or "") for k in ("抱歉", "找不到", "404", "Not Found")):
            return {"list": []}

        pic = ""
        first_imgs = _extract_page_images(html)
        if first_imgs:
            pic = _fix(first_imgs[0])

        return {"list": [{
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": title,
            "vod_year": "",
            "vod_play_from": "图集",
            "vod_play_url": f"在线观看${vid}",
        }]}

    def playerContent(self, flag, id, vipFlags):
        header = json.dumps({"User-Agent": UA, "Referer": HOST + "/"})

        # 直接是图片
        if re.search(r'\.(jpg|jpeg|png|webp|gif)(\?|$)', id or '', re.I):
            return {"parse": 0, "playUrl": "", "url": f"pics://{id}", "header": header}

        html = _get(id, referer=HOST + "/")
        if not html:
            return {"parse": 1, "playUrl": "", "url": id, "header": header}

        images = _collect_detail_images(id, html)
        if images:
            pics = "&&".join(images)
            return {"parse": 0, "playUrl": "", "url": f"pics://{pics}", "header": header}

        return {"parse": 1, "playUrl": "", "url": id, "header": header}


if __name__ == '__main__':
    sp = Spider()
    sp.init('')
    print('== 分类 ==')
    print(json.dumps(sp.homeContent(True), ensure_ascii=False, indent=2))

    print('== 列表 第1页 ==')
    c1 = sp.categoryContent("1", "1", False, {})
    print(f'第1页: {len(c1["list"])} 条, pagecount={c1["pagecount"]}')
    if c1["list"]:
        print(json.dumps(c1["list"][:2], ensure_ascii=False, indent=2))

    print('== 列表 第2页 ==')
    c2 = sp.categoryContent("1", "2", False, {})
    print(f'第2页: {len(c2["list"])} 条, pagecount={c2["pagecount"]}')
    if c2["list"]:
        print(json.dumps(c2["list"][:2], ensure_ascii=False, indent=2))

    if c1["list"]:
        print('== 详情 ==')
        d = sp.detailContent([c1["list"][0]["vod_id"]])
        if d["list"]:
            v = d["list"][0]
            print(json.dumps({"name": v["vod_name"], "pic": v["vod_pic"][:60]},
                             ensure_ascii=False, indent=2))
            print('== 播放 (并发抓全部页) ==')
            p = sp.playerContent("图集", v["vod_play_url"].split("$")[1], {})
            imgs = p["url"][len("pics://"):].split("&&") if p["url"].startswith("pics://") else []
            print(f'共 {len(imgs)} 张')
            for u in imgs[:5]:
                print(' ', u)