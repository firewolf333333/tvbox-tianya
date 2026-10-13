# -*- coding: utf-8 -*-
"""
TVBox 图片站源 - 169tp (www.169tp.com)
================================================
织梦 DedeCMS 风格图片站，GB18030/GB2312 编码。
适配图片模板（pics:// 图库协议）：
- 列表：解析 <li> 卡片（<a href><img><p>标题</p>）
- 详情：单集"在线观看$详情URL"
- 播放：抓取详情页全部内容大图，pics:// 拼接

实测 (2026-09-25)：
  页面 GB 编码，无 Cloudflare。
  首页导航共 12 个分类。
  详情页 HTML 源码直接包含大图（allimg/uploads 路径）。
"""

import sys
import re
import json
from urllib.parse import quote

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


HOST = "https://www.169tp.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# 首页导航完整分类（12 个）
CATS = [
    ("ziranfengguang", "自然风光"),
    ("xingganmeinv",   "性感美女"),
    ("tupiangushi",    "图片故事"),
    ("wangyouzipai",   "网友自拍"),
    ("gaoxiaotupian",  "搞笑图片"),
    ("rentiyishu",     "人体艺术"),
    ("meishitupian",   "美食图片"),
    ("guoneimeinv",    "国内美女"),
    ("shoujibizhi",    "手机壁纸"),
    ("gaogensiwa",     "高跟丝袜"),
    ("touxiangdaquan", "头像大全"),
    ("xiyangmeinv",    "西洋美女"),
]
CAT_DIR = {c[0]: c[0] for c in CATS}

ART_RE = re.compile(r'/\d{4}/\d{4}/\d+\.html')
IMG_TAG_RE = re.compile(r'<img[^>]+>', re.I)
BAD_IMG = re.compile(r'(templets|/js/|/css/|favicon|logo|/skin/|spacer|blank\.gif|btn_|/icon|qrcode|weixin|weibo)', re.I)
GOOD_IMG = re.compile(r'(allimg|uploads|/up/|/pic/|/photo/)', re.I)

_CACHE = {}


def _get(url, referer=None):
    if not url:
        return ""
    if url in _CACHE:
        return _CACHE[url]
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer or (HOST + "/"),
    }
    text = ""
    try:
        if requests:
            r = requests.get(url, headers=headers, timeout=20)
            text = r.content.decode("gb18030", errors="ignore")
        else:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("gb18030", errors="ignore")
    except Exception as e:
        print(f"[GET ERR] {url} -> {e}")
        text = ""
    if len(_CACHE) > 64:
        _CACHE.clear()
    _CACHE[url] = text
    return text


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


def parse_list(html):
    """解析 <li> 卡片列表（首页与分类页通用）"""
    result = []
    if not html:
        return result
    seen = set()
    for li in re.findall(r'<li[^>]*>(.*?)</li>', html, re.S):
        img_m = re.search(r'<img[^>]+(?:src|data-src|data-original)="([^"]+)"', li, re.I)
        href_m = re.search(r'href="([^"]+)"', li)
        if not img_m or not href_m:
            continue
        href = _fix(href_m.group(1))
        if href in seen or not ART_RE.search(href):
            continue
        pic = _fix(img_m.group(1))
        if BAD_IMG.search(pic) and not GOOD_IMG.search(pic):
            continue
        seen.add(href)

        name = ""
        p = re.search(r'<p[^>]*>([^<]+)</p>', li)
        if p:
            name = p.group(1).strip()
        if not name:
            alt = re.search(r'alt="([^"]+)"', img_m.group(0))
            if alt:
                name = alt.group(1).strip()
        if not name:
            name = re.sub(r'<[^>]+>', '', li).strip()[:40]
        if not name:
            continue

        result.append({
            "vod_id": href,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": "",
            "vod_play_from": "图集",
        })
    return result


def parse_pagecount(html):
    ns = [int(x) for x in re.findall(r'(?:\?|&|/)page[=/]?(\d+)', html or "")]
    return max(ns) if ns else 1


def _extract_imgs(html):
    """从详情页提取内容大图；优先定位内容区，否则全页过滤"""
    if not html:
        return []
    zone = html
    strict = True
    m = re.search(
        r'<div[^>]+(?:id|class)="[^"]*(?:content|article|neirong|txt|text|main)[^"]*"[^>]*>(.*?)</div>',
        html, re.S | re.I)
    if m and len(m.group(1)) > 400:
        zone = m.group(1)
        strict = False

    out, seen = [], set()
    for tag in IMG_TAG_RE.findall(zone):
        src = ""
        for attr in ("src", "data-src", "data-original", "data-echo", "data-lazy-src"):
            mm = re.search(attr + r'="([^"]+)"', tag, re.I)
            if mm and mm.group(1).strip():
                src = mm.group(1).strip()
                break
        if not src or src.startswith("data:"):
            continue
        if BAD_IMG.search(src):
            continue
        if strict and not GOOD_IMG.search(src):
            continue
        u = _fix(src)
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


class Spider(BaseSpider):
    def __init__(self): pass
    def getName(self): return "169图片"
    def init(self, extend=""): pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|avi|mkv|ts|mov|jpg|jpeg|png|webp|gif)(\?|$)', url or '', re.I))
    def manualVideoCheck(self): return False

    def homeContent(self, filter=False):
        return {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATS], "filters": {}}

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
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            url = f"{HOST}/{cat}/"
            if pg > 1:
                url += f"page/{pg}.html" if pg else ""
            html = _get(url, referer=HOST + "/")
            videos = parse_list(html)
            if not videos and pg == 1:
                # 兜底：试 ?page=N 形式
                html = _get(f"{HOST}/{cat}/?page={pg}", referer=HOST + "/")
                videos = parse_list(html)
            pagecount = parse_pagecount(html) if videos else 1
            if pg > pagecount:
                pagecount = pg
            return {"list": videos, "page": pg, "pagecount": pagecount,
                    "limit": len(videos) or 20, "total": -1}
        except Exception as e:
            print(f"[categoryContent] {e}")
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

    def searchContent(self, key, quick=False):
        try:
            url = f"{HOST}/search/?key={quote(key or '')}"
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
                title = m.group(1).split("-")[0].split("_")[0].strip()
        if any(k in (title or "") for k in ("抱歉", "找不到", "404", "Not Found")):
            return {"list": []}

        imgs = _extract_imgs(html)
        pic = imgs[0] if imgs else ""

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
        # 已是图片直链
        if re.search(r'\.(jpg|jpeg|png|webp|gif)(\?|$)', id or '', re.I):
            return {"parse": 0, "playUrl": "", "url": f"pics://{id}", "header": header}

        html = _get(id, referer=HOST + "/")
        imgs = _extract_imgs(html)
        if imgs:
            return {"parse": 0, "playUrl": "",
                    "url": "pics://" + "&&".join(imgs), "header": header}
        return {"parse": 1, "playUrl": "", "url": id, "header": header}


if __name__ == '__main__':
    sp = Spider()
    sp.init('')
    print('== 分类 ==')
    print(json.dumps(sp.homeContent(True), ensure_ascii=False, indent=2))
    print('== 列表(前3) ==')
    c = sp.categoryContent("rentiyishu", "1", False, {})
    print(json.dumps({"list": c["list"][:3], "total": len(c["list"]),
                      "pagecount": c["pagecount"]}, ensure_ascii=False, indent=2))
    if c["list"]:
        print('== 详情 ==')
        d = sp.detailContent([c["list"][0]["vod_id"]])
        if d["list"]:
            v = d["list"][0]
            print(json.dumps({"name": v["vod_name"], "pic": v["vod_pic"][:60],
                              "play_url": v["vod_play_url"]}, ensure_ascii=False, indent=2))
            p = sp.playerContent("图集", v["vod_play_url"].split("$")[1], {})
            imgs = p["url"][len("pics://"):].split("&&") if p["url"].startswith("pics://") else []
            print(f'播放: {len(imgs)} pics, parse={p["parse"]}')