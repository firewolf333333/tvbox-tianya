# -*- coding: utf-8 -*-
"""
TVBox 图片站源 - 热图站 (www.retu8.com)
========================================
GB2312 编码。织梦 DedeCMS 风格图片站。

关键：
- 详情页翻页（页码页/下一页）存在被跳转外站的风险（曾 302 到 0505.co），
  一律不抓分页页；总图片数只在详情第一页取：
  描述"共有N张图片，分为M页"（精确）→ 分页器末页页码 × 每页张数（估算）
- 大图路径规律不统一（历史原因）：新帖 pic{ID[:3]}/{ID}-N.jpg 如 pic520/52079-1.jpg；
  老帖 pic{ID[:2]}/{ID补零5位}-N.jpg 如 pic55/05544-1.jpg。一律用详情第一张
  真实大图 src 推导前缀模板，再拼接出全部 N 张，不再按 ID 猜测目录
- 单集结构 + pics:// 多图，TVBox 图片播放器滑动浏览
"""

import sys
import re
import json

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


HOST = "https://www.retu8.com"
HOST_IMG = "https://img.retu8.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# ============================================================
# 分类（一级导航 + 独立栏目）
# ============================================================
CATS = [
    ("1", "美女图片", "html/meinv"),
    ("2", "唯美图片", "html/weimei"),
    ("3", "动漫卡通", "html/dongman"),
    ("4", "图看世界", "html/shijie"),
]
CAT_DIR = {c[0]: c[2] for c in CATS}

_CAT_PAGE_PATTERN = {}

# 大图模板：https://img.retu8.com/pic55/05544-1.jpg
_TEMPLATE_RE = re.compile(
    r'^(.*?[-_])(\d+)(\.(?:jpg|jpeg|png|gif|webp))(?:\?.*)?$', re.I)


# ---------------------------------------------------------------- 基础
def _get(url, referer=None, timeout=20):
    if not url:
        return ""
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        # 不做 br/gzip 内容协商，避免压缩内容解码异常导致正文乱码
        "Accept-Encoding": "identity",
        "Referer": referer or (HOST + "/"),
    }
    try:
        if requests:
            r = requests.get(url, headers=headers, timeout=timeout)
            return r.content.decode("gb18030", errors="ignore")
        else:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("gb18030", errors="ignore")
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


def _is_ui_image(u):
    if not u:
        return True
    low = u.lower()
    for kw in ('/css/', '/js/', 'logo', 'icon', 'btn', 'spacer', 'blank',
               'loading', 'banner', '/ad/', 'ad_', 'share', 'weixin',
               'weibo', 'avatar', 'copyright', 'footer'):
        if kw in low:
            return True
    return False


# ---------------------------------------------------------------- 列表解析
def parse_list(html):
    result = []
    if not html:
        return result

    seen = set()
    for li in re.findall(r'<li[^>]*>.*?</li>', html, re.S):
        am = re.search(r'<a[^>]+href="([^"]+\.html?)"', li)
        if not am:
            continue
        href = _fix(am.group(1))

        im = re.search(r'<img[^>]+(?:data-original|data-src|src)="([^"]+)"', li)
        pic = _fix(im.group(1)) if im else ""

        name = ""
        sm = re.search(r'<span[^>]*>([^<]+)</span>', li)
        if sm:
            name = sm.group(1).strip()
        if not name:
            am2 = re.search(r'alt="([^"]+)"', li)
            if am2:
                name = am2.group(1).strip()
        if not name:
            continue
        if _is_ui_image(pic):
            continue
        if href in seen:
            continue
        seen.add(href)

        result.append({
            "vod_id": href,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": "",
            "vod_play_from": "图集",
        })
    return result


def _has_list_items(html):
    if not html or len(html) < 500:
        return False
    return bool(re.search(r'<li[^>]*>[\s\S]*?<a[^>]+href="[^"]+\.html?"', html))


# ---------------------------------------------------------------- 分类翻页
def _fetch_cat_page(cat, pg):
    if pg <= 1:
        return _get(f"{HOST}/{cat}/", referer=HOST + "/")

    pattern = _CAT_PAGE_PATTERN.get(cat)
    if pattern:
        url = pattern.replace("{N}", str(pg))
        html = _get(url, referer=f"{HOST}/{cat}/")
        if html and _has_list_items(html):
            return html
        _CAT_PAGE_PATTERN.pop(cat, None)

    candidates = [
        f"{HOST}/{cat}/index_{{N}}.html",
        f"{HOST}/{cat}/list_{{N}}.html",
        f"{HOST}/{cat}/{{N}}.html",
        f"{HOST}/{cat}/index_{{N}}.htm",
        f"{HOST}/{cat}/list_{{N}}.htm",
        f"{HOST}/{cat}/{{N}}.htm",
        f"{HOST}/{cat}/?page={{N}}",
    ]
    for pat in candidates:
        test_url = pat.replace("{N}", str(pg))
        html = _get(test_url, referer=f"{HOST}/{cat}/")
        if html and _has_list_items(html):
            _CAT_PAGE_PATTERN[cat] = pat
            print(f"[pagination] {cat} -> {pat}")
            return html
    return ""


# ---------------------------------------------------------------- 详情页图片
def _extract_id(detail_url):
    m = re.search(r'/([a-zA-Z]+)(\d+)\.html?$', detail_url or '')
    if m:
        return m.group(2)
    m = re.search(r'/(\d+)\.html?$', detail_url or '')
    if m:
        return m.group(1)
    return None


def _extract_total(html, per_page=0):
    """提取总图片数（只在详情第一页取，不抓分页页）。

    优先级：
    1) 描述里精确的"共有N张图片，分为M页 / 共N张"
    2) 分页器页码链接（含 ..19 这种省略号样式）的末页页码 × 每页张数
    3) 单页图集：直接用第一页实际张数
    """
    if not html:
        return 1
    for pat in (r'共有\s*(\d+)\s*张', r'共\s*(\d+)\s*张',
                r'<li>\s*<a[^>]*>\s*\d+\s*/\s*(\d+)', r'\b1\s*/\s*(\d+)\s*:'):
        m = re.search(pat, html)
        if m:
            try:
                n = int(m.group(1))
                if 1 <= n <= 5000:
                    return n
            except ValueError:
                pass
    pg = re.search(
        r'<div[^>]+class="[^"]*page[^"]*"[^>]*>([\s\S]*?)</div>', html, re.I)
    if pg and per_page > 0:
        nums = [int(x) for x in re.findall(r'>(\d+)</a>', pg.group(1))]
        if nums:
            n = max(nums) * per_page
            if 1 <= n <= 5000:
                return n
    return per_page if per_page > 0 else 1


def _first_page_imgs(html):
    """详情第一页内容区（<div class="pp ...">）里的真实大图 src。"""
    m = re.search(r'<div[^>]+class="[^"]*pp[^"]*"[^>]*>', html, re.I)
    if not m:
        return []
    seg = html[m.end():]
    e = re.search(r'<div[^>]+class="[^"]*page[^"]*"[^>]*>', seg, re.I)
    if e:
        seg = seg[:e.start()]
    else:
        d = seg.find('</div>')
        if d >= 0:
            seg = seg[:d]
    return [x.group(1) for x in re.finditer(r'<img[^>]+src="([^"]+)"', seg, re.I)]


def _collect_images(detail_url, html):
    """按详情第一页的真实大图推导整组图 URL；分页页可能跳外站，一律不抓。"""
    images = []
    seen = set()

    def add(u):
        u = _fix(u)
        low = u.lower()
        if not u or u in seen or _is_ui_image(u) or '/slt/' in low:
            return
        seen.add(u)
        images.append(u)

    pp_srcs = _first_page_imgs(html)
    page_srcs = [u for u in pp_srcs
                 if 'img.retu8.com' in u and '/slt/' not in u.lower()]
    for u in page_srcs:
        add(u)

    if not images:
        # 页面结构异常：退回全页 src 收集 img.retu8.com 大图
        for mm in re.finditer(r'src="(https?://img\.retu8\.com/[^"]+)"', html):
            add(mm.group(1))
    if not images:
        print(f"[detail] 页面内未找到大图: {detail_url}")
        return []

    per_page = len(page_srcs) or 1
    total = _extract_total(html, per_page)

    # 从第一张真实大图推模板：https://img.retu8.com/pic55/05544-1.jpg
    # -> https://img.retu8.com/pic55/05544- + N + .jpg（老帖补零位、目录一并保留）
    m = _TEMPLATE_RE.match(images[0])
    if m and total > len(images):
        prefix, ext = m.group(1), m.group(3)
        for n in range(1, total + 1):
            add(f"{prefix}{n}{ext}")

    print(f"[detail] id={_extract_id(detail_url)} first={images[0]} "
          f"total={total} -> {len(images)} 张")
    return images


# ---------------------------------------------------------------- Spider
class Spider(BaseSpider):
    def __init__(self): pass
    def getName(self): return "热图站"
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
            print(f"[category] tid={tid} pg={pg} -> {len(videos)} 条")
            if videos:
                return {"list": videos, "page": pg, "pagecount": pg + 1,
                        "limit": len(videos), "total": -1}
            return {"list": [], "page": pg, "pagecount": pg,
                    "limit": 0, "total": 0}
        except Exception as e:
            print(f"[categoryContent] {e}")
            return {"list": [], "page": pg, "pagecount": pg, "limit": 0, "total": 0}

    def searchContent(self, key, quick=False):
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
        m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html, re.I)
        if m:
            title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not title:
            m = re.search(r'<title>([^<]+)</title>', html, re.I)
            if m:
                title = m.group(1).split("-")[0].strip()

        if any(k in (title or "") for k in ("抱歉", "找不到", "404", "Not Found")):
            return {"list": []}

        images = _collect_images(vid, html)
        if not images:
            return {"list": []}

        # 单集结构：一集"在线观看"，点开后 TVBox 用 pics:// 滑动浏览全部图
        return {"list": [{
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": images[0],
            "vod_content": f"{title}（共{len(images)}张）",
            "vod_year": "",
            "vod_play_from": "图集",
            "vod_play_url": f"在线观看${vid}",
        }]}

    def playerContent(self, flag, id, vipFlags):
        header = json.dumps({"User-Agent": UA, "Referer": HOST + "/"})

        # 单张图片直链
        if re.search(r'\.(jpg|jpeg|png|webp|gif)(\?|$)', id or '', re.I):
            return {"parse": 0, "playUrl": "", "url": f"pics://{id}", "header": header}

        # 详情页 URL → 生成全部图片的 pics:// 列表
        html = _get(id, referer=HOST + "/")
        if html:
            images = _collect_images(id, html)
            if images:
                pics = "&&".join(images)
                return {"parse": 0, "playUrl": "", "url": f"pics://{pics}", "header": header}

        return {"parse": 1, "playUrl": "", "url": id, "header": header}


if __name__ == '__main__':
    sp = Spider()
    sp.init('')

    print('== 分类 (共%d) ==' % len(CATS))
    for tid, name, _ in CATS:
        c = sp.categoryContent(tid, "1", False, {})
        print(f'  [{tid}] {name}: {len(c["list"])} 条')

    print()
    print('== 详情抽查 ==')
    for name, url in [
        ("新帖-分页估算", "https://www.retu8.com/html/yijing/czbb52079.htm"),
        ("老帖-描述精确", "https://www.retu8.com/html/wangluo/ifg5544.htm"),
        ("长图集", "https://www.retu8.com/html/xinggan/ckvx42481.htm"),
    ]:
        print(f'-- {name} --')
        d = sp.detailContent([url])
        if not d["list"]:
            print("  无数据")
            continue
        v = d["list"][0]
        print(f'  标题: {v["vod_name"]}')
        print(f'  内容: {v["vod_content"]}')
        p = sp.playerContent("图集", v["vod_play_url"].split("$")[1], {})
        imgs = p["url"][len("pics://"):].split("&&") if p["url"].startswith("pics://") else []
        print(f'  pics 共 {len(imgs)} 张')