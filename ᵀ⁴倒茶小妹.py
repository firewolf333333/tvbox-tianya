# -*- coding: utf-8 -*-
# 倒茶小妹 https://y5z6a7b8.chamm238.xyz  T4 版（原 JS 源转写 + 播放线路修复，2026-11-04）
# ---------------------------------------------------------------------------
# 站点结构（2026-11-04 实站探测）：
#   首页    /topic/                  根路径 / 是「点击进入」静态门页（无任何列表，
#                                    照原 JS 取 / 会得到空首页）——已改为取 /topic/
#   分类    /vodtype/{tid}-{pg}.html 卡片 article.post + a[href*=/voddetail/] + img.lazyload[data-src]
#   详情    /voddetail/{vid}.html    h1.entry-title 标题 / entry-content 内封面图 /
#                                    meta description（= 标题 +「剧情:」+ 简介）
#   播放    /vodplay/{vid}-{sid}-{nid}.html
#                                   页内 var player_aaaa={"url":"%68%74%74%70...","encrypt":1,"from":"sjp"}
#                                   url 是 URL 编码的 m3u8 直链；实测 m3u8 不带 UA 取回 403，
#                                   带 UA 取回 200 + application/vnd.apple.mpegurl
#   搜索    /vodsearch/{kw}----------{pg}---.html
#
# 播放线路修复（用户报「所有线路都是一样的内容」）：
#   站点详情页标签区把「播放线路一」与「备用线路二」两条锚都指向同一个地址
#   /vodplay/{vid}-1-1.html（同一 href，仅标签文案不同）；原 JS 按锚逐条出线，
#   于是详情里会出现多条线路，但它们的播放目标是同一个 → 点哪条都放同一部视频。
#   实测：站点每个视频只有 sid=1 一条真实源（sid=2/3 页存在但 player_aaaa.url 恒为空）。
#   本版改为按真实播放目标 (vid, sid, nid) 去重：
#     · 指向同一目标的多余标签合并为一条线路（不再出现两条同内容线路）；
#     · 只有目标确实不同的才拆成独立线路；
#     · 同一 sid 下的多个 nid 归一为同一条线路的多集。
#
# 其余随转写一并修掉的缺陷：
#   ① 首页取 / → 门页，列表恒空；改取 /topic/。
#   ② 详情封面原取首个 img.lazyload → 命中站点头像 favicon（/template/chamm/img/favicon.png）；
#      改取详情正文（entry-content）封面图，再按 upload/vod 路径兜底。
#   ③ 分类按站点导航补全：原 JS 31 类，站点实为 32 类（缺「66 日本素人」）。
#   ④ 简介取站内 meta description 去掉标题前缀与「剧情:」，站点无简介时留空，
#      不写任何品牌/推广语（用户铁律）；站点详情页无演员/导演/类型数据，故不臆造这些字段。
#   ⑤ py2(Jython 2.7) / py3 双运行时归一：中文字面量统一 u 前缀，取网的 url 与头值
#      按运行时区分 bytes/str，入口补齐 *args/**kwargs 弹性签名与页码 int 归一。
# ---------------------------------------------------------------------------
import re
import sys
import json

try:
    from urllib.parse import urljoin, quote, unquote
except ImportError:
    from urlparse import urljoin
    from urllib import quote, unquote

try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib2 import urlopen, Request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getName(self):
            return ""

        def init(self, extend=""):
            pass

        def getDependence(self):
            return []

        def destroy(self):
            pass

        def isVideoFormat(self, url):
            return False

        def manualVideoCheck(self):
            return 0

        def localProxy(self, params):
            return [404, "text/plain", b""]

        def action(self, action):
            return {}

try:
    _STR = basestring
except NameError:
    _STR = str

try:
    _unicode = unicode
except NameError:
    _unicode = str


def _txt(x):
    if x is None:
        return u""
    if isinstance(x, bytes):
        return x.decode("utf-8", "ignore")
    if isinstance(x, _unicode):
        return x
    if isinstance(x, _STR):
        try:
            return x.decode("utf-8")
        except Exception:
            return x.decode("utf-8", "ignore")
    return _unicode(x)


def _strip(s):
    return re.sub(r"<[^>]+>", "", _txt(s)).strip()


def _clean(s):
    s = _txt(s)
    s = s.replace("&quot;", '"').replace("&#39;", "'").replace("&gt;", ">")
    s = s.replace("&lt;", "<").replace("&nbsp;", " ").replace("&amp;", "&")
    return s.strip()


def _unquote(s):
    t = _txt(s).strip()
    if not t:
        return u""
    try:
        if sys.version_info[0] == 2:
            return unquote(t.encode("utf-8")).decode("utf-8", "ignore")
        return unquote(t)
    except Exception:
        return t


def _quote(s):
    t = _txt(s)
    try:
        if sys.version_info[0] == 2:
            return quote(t.encode("utf-8"))
        return quote(t)
    except Exception:
        return t


def _abs(base, url):
    url = _txt(url).strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(base, url)


def _b64decode(s):
    t = _txt(s).strip()
    if not t:
        return u""
    try:
        import base64
        pad = len(t) % 4
        if pad:
            t = t + "=" * (4 - pad)
        raw = base64.b64decode(t)
        if isinstance(raw, bytes):
            try:
                return raw.decode("utf-8")
            except Exception:
                return raw.decode("utf-8", "ignore")
        return _txt(raw)
    except Exception:
        return u""


def _json_obj(html, key):
    # MacCMS 播放变量（player_aaaa / player_data）用大括号平衡扫描取对象，
    # 不用贪婪正则吞掉整页脚本，也不用 [^}]+ 这种遇到嵌套就截断的写法。
    m = re.search(r"\b" + key + r"\s*=\s*\{", html)
    if not m:
        return None
    start = html.find("{", m.start())
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(html)):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:i + 1])
                except Exception:
                    return None
    return None


class Spider(BaseSpider):
    NAME = u"倒茶小妹"
    SITE_URL = "https://y5z6a7b8.chamm238.xyz"
    HOME_PATH = u"/topic/"
    DEFAULT_PIC = u"https://pic.rmb.bdstatic.com/bjh/user/default.png"
    # 站点导航分类（32 个，顺序与站点导航一致；原 JS 少「66 日本素人」已补全）
    CLASSES = [
        (u"6", u"麻豆视频"), (u"7", u"91制片厂"), (u"8", u"天美传媒"),
        (u"9", u"蜜桃传媒"), (u"10", u"皇家华人"), (u"11", u"星空传媒"),
        (u"12", u"精东影业"), (u"20", u"乐播传媒"), (u"21", u"兔子先生"),
        (u"22", u"杏吧原创"), (u"23", u"玩偶姐姐"), (u"24", u"mini传媒"),
        (u"25", u"大象传媒"), (u"26", u"性视界"), (u"30", u"成人头条"),
        (u"31", u"开心鬼传媒"), (u"37", u"PsychoPorn"), (u"32", u"糖心Vlog"),
        (u"33", u"萝莉社"), (u"34", u"乌鸦传媒"), (u"28", u"国产精品"),
        (u"29", u"华语AV"), (u"35", u"黑料吃瓜"), (u"15", u"学生合集"),
        (u"59", u"乱伦精品"), (u"60", u"探花约炮"), (u"61", u"日本无码"),
        (u"62", u"主播网红"), (u"63", u"欧美精品"), (u"64", u"动漫禁漫"),
        (u"65", u"日本有码"), (u"66", u"日本素人"),
    ]

    def getName(self):
        return self.NAME

    def init(self, extend=""):
        self.site_url = self.SITE_URL
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.site_url + "/",
        }
        self.default_pic = self.DEFAULT_PIC
        ext = extend
        if isinstance(ext, dict) and ext.get("host"):
            self.site_url = _txt(ext.get("host")).rstrip("/")
            self.headers["Referer"] = self.site_url + "/"

    def _ensure(self):
        if not getattr(self, "site_url", None):
            self.init()

    def getDependence(self):
        return []

    def destroy(self):
        pass

    def close(self):
        self.destroy()

    def action(self, action=None, *args, **kwargs):
        return {}

    def isVideoFormat(self, url=None, *args, **kwargs):
        try:
            return bool(re.search(r"\.(m3u8|mp4|flv|ts|mkv|mov)([?#&/]|$)", _txt(url), re.I))
        except Exception:
            return False

    def manualVideoCheck(self, *args, **kwargs):
        return 0

    def localProxy(self, params=None, *args, **kwargs):
        # 本源无代理需求，按 T4 契约返回空列表
        return []

    # ========== 网络 ==========

    def _bytes(self, x):
        # 取网编码形态必须按运行时区分，否则会「修好一边、弄空另一边」：
        # py2(Jython 2.7，盒端)：url/头值必须是 bytes，传 unicode 抛 TypeError；
        # py3（本机校验）：urllib 只接受 str，传 bytes 抛 unknown url type: b'https
        if sys.version_info[0] != 2:
            return x
        if isinstance(x, bytes):
            return x
        try:
            return x.encode("utf-8")
        except Exception:
            return x

    def _get(self, url, referer=None):
        self._ensure()
        if not url:
            return u""
        url = self._bytes(_abs(self.site_url, url))
        headers = {}
        for k, v in self.headers.items():
            headers[self._bytes(k)] = self._bytes(v)
        if referer:
            headers[self._bytes("Referer")] = self._bytes(_abs(self.site_url, referer))
        try:
            resp = urlopen(Request(url, headers=headers), timeout=12)
            raw = resp.read()
            try:
                enc = _txt(resp.headers.get("Content-Encoding", "")).lower()
            except Exception:
                enc = ""
            if "gzip" in enc:
                try:
                    import gzip
                    try:
                        from io import BytesIO
                    except ImportError:
                        from StringIO import StringIO as BytesIO
                    raw = gzip.GzipFile(fileobj=BytesIO(raw)).read()
                except Exception:
                    pass
            if isinstance(raw, bytes):
                try:
                    return raw.decode("utf-8")
                except Exception:
                    try:
                        return raw.decode("gbk")
                    except Exception:
                        return raw.decode("utf-8", "ignore")
            return _txt(raw)
        except Exception:
            return u""

    def _probe_media(self, url):
        # 真直链门禁：parse=0 只能用于实测确认的媒体地址（本站 m3u8 必须带 UA 才 200）。
        # True=确认媒体；False=确认非媒体（降级 parse=1，不冒充直链）；None=探测失败（不判死）。
        if not url:
            return False
        try:
            headers = {
                self._bytes("User-Agent"): self._bytes(self.headers.get("User-Agent", "")),
                self._bytes("Referer"): self._bytes(self.site_url + "/"),
            }
            resp = urlopen(Request(self._bytes(url), headers=headers), timeout=8)
            raw = resp.read(2048)
            head = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else _txt(raw)
            if "#EXTM3U" in head:
                return True
            try:
                ctype = _txt(resp.headers.get("Content-Type", "")).lower()
            except Exception:
                ctype = ""
            if "mpegurl" in ctype or ctype.startswith("video/") or ctype.startswith("audio/"):
                return True
            return False
        except Exception:
            return None

    # ========== 解析 ==========

    def _parse_list(self, html):
        self._ensure()
        videos = []
        seen = set()
        if not html:
            return videos
        for art in re.findall(r'<article[^>]*class="[^"]*\bpost\b[^"]*"[\s\S]*?</article>', html):
            m = re.search(r'href="[^"]*/voddetail/(\d+)\.html"', art)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            name = u""
            t = re.search(r'<h[12] class="entry-title">\s*<a[^>]*title="([^"]*)"', art)
            if not t:
                t = re.search(r'<a[^>]*title="([^"]*)"', art)
            if t:
                name = _clean(t.group(1))
            if not name:
                a = re.search(r'<h[12] class="entry-title">\s*<a[^>]*>([\s\S]*?)</a>', art)
                name = _strip(a.group(1)) if a else u""
            if not name:
                t = re.search(r'<h[12] class="entry-title">([\s\S]*?)</h[12]>', art)
                name = _strip(t.group(1)) if t else u""
            if not name:
                im = re.search(r'<img[^>]*alt="([^"]*)"', art)
                name = _clean(im.group(1)) if im else u""
            if not name:
                continue
            pic = re.search(r'class="[^"]*lazyload[^"]*"[^>]*data-src="([^"]+)"', art)
            if not pic:
                pic = re.search(r'data-src="([^"]+)"', art)
            if not pic:
                pic = re.search(r'<img[^>]*\ssrc="(https?://[^"]+)"', art)
            pic = _abs(self.site_url, pic.group(1)) if pic else u""
            remark = u""
            rm = re.search(r'<span class="meta-category">[\s\S]*?<a[^>]*>([\s\S]*?)</a>', art)
            if rm:
                remark = _strip(rm.group(1))
            if not remark:
                rm = re.search(r'<a[^>]*rel="category"[^>]*>([\s\S]*?)</a>', art)
                if rm:
                    remark = _strip(rm.group(1))
            seen.add(vid)
            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic if pic else self.default_pic,
                "vod_remarks": remark,
            })
        return videos

    def _calc_pagecount(self, html, pattern):
        nums = []
        for n in re.findall(pattern, html):
            try:
                n = int(n)
            except Exception:
                continue
            if n > 0:
                nums.append(n)
        return max(nums) if nums else 0

    def _parse_detail_pic(self, html):
        # 正文（entry-content）里的封面图优先；站点头像/favicon 一律排除。
        m = re.search(r'<div class="entry-content[^"]*"[^>]*>([\s\S]*?)</div>', html)
        if m:
            im = re.search(r'<img[^>]*(?:data-src|src)="([^"]+)"', m.group(1))
            if im:
                pic = _abs(self.site_url, im.group(1))
                if pic and "favicon" not in pic:
                    return pic
        for pat in (r'<img[^>]+(?:data-src|src)="([^"]*upload/vod[^"]*)"',
                    r'<img[^>]*class="[^"]*lazyload[^"]*"[^>]*data-src="([^"]+)"'):
            m = re.search(pat, html)
            if m:
                pic = _abs(self.site_url, m.group(1))
                if pic and "favicon" not in pic:
                    return pic
        return u""

    def _parse_detail_content(self, html, title):
        m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
        if not m:
            return u""
        desc = _clean(m.group(1))
        title = _txt(title).strip()
        if title and desc.startswith(title):
            desc = desc[len(title):].strip()
        for pre in (u"剧情:", u"剧情：", u"简介:", u"简介："):
            if desc.startswith(pre):
                desc = desc[len(pre):].strip()
        if desc == title:
            desc = u""
        return desc

    def _parse_play_lines(self, html, title):
        # 关键修复：按真实播放目标 (vid, sid, nid) 去重，同一 href 的多条标签合并为一条线路。
        targets = []
        seen = set()
        names = {}
        title = _txt(title).strip()
        for m in re.finditer(r'<a[^>]+href="(/vodplay/(\d+)-(\d+)-(\d+)\.html)"[^>]*>([\s\S]*?)</a>', html):
            path, sid, nid = m.group(1), m.group(3), m.group(4)
            label = _strip(m.group(5))
            key = sid + "-" + nid
            if key not in seen:
                seen.add(key)
                targets.append((sid, nid, path))
            if sid in names:
                continue
            if label and label != title and not label.startswith(u"http"):
                names[sid] = label
        return targets, names

    def _build_play(self, targets, names, vid):
        order = []
        groups = {}
        for sid, nid, path in targets:
            if sid not in groups:
                groups[sid] = []
                order.append(sid)
            groups[sid].append((nid, path))
        play_from = []
        play_url = []
        for idx, sid in enumerate(order):
            eps = groups[sid]
            ep_items = []
            for nid, path in eps:
                ep_name = u"正片" if len(eps) == 1 else u"第{0}集".format(nid)
                ep_items.append(u"{0}${1}".format(ep_name, _abs(self.site_url, path)))
            if not ep_items:
                continue
            play_from.append(names.get(sid) or u"线路{0}".format(idx + 1))
            play_url.append("#".join(ep_items))
        return play_from, play_url

    # ========== 首页 ==========

    def _home_html(self):
        # 根路径 / 是「点击进入」门页，取它拿不到任何卡片；首页固定取 /topic/。
        html = self._get(self.site_url + self.HOME_PATH)
        if not self._parse_list(html):
            html = self._get(self.site_url + u"/vodtype/6-1.html")
        return html

    def homeContent(self, filter=None, *args, **kwargs):
        self._ensure()
        categories = [{"type_id": k, "type_name": v} for k, v in self.CLASSES]
        videos = []
        try:
            videos = self._parse_list(self._home_html())
        except Exception:
            videos = []
        return {"class": categories, "list": videos[:30], "filters": {}}

    def homeVideoContent(self, *args, **kwargs):
        self._ensure()
        videos = []
        try:
            videos = self._parse_list(self._home_html())
        except Exception:
            videos = []
        return {"list": videos[:30]}

    # ========== 分类 ==========

    def categoryContent(self, tid, pg=None, filter=None, extend=None, *args, **kwargs):
        self._ensure()
        try:
            pg = int(pg) if pg else 1
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        tid = _txt(tid).strip() or u"6"
        url = self.site_url + "/vodtype/{0}-{1}.html".format(tid, pg)
        html = self._get(url)
        videos = self._parse_list(html)
        pagecount = self._calc_pagecount(html, r'/vodtype/{0}-(\d+)\.html'.format(tid)) or pg
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(videos),
            "total": 0,
        }

    # ========== 搜索 ==========

    def searchContent(self, key, quick=False, pg="1", *args, **kwargs):
        self._ensure()
        try:
            pg = int(pg) if pg else 1
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        url = self.site_url + "/vodsearch/{0}----------{1}---.html".format(_quote(key), pg)
        html = self._get(url)
        videos = self._parse_list(html)
        pagecount = self._calc_pagecount(html, r'-(\d+)---\.html') or pg
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(videos),
            "total": 0,
        }

    # ========== 详情 ==========

    def detailContent(self, ids=None, *args, **kwargs):
        self._ensure()
        if not ids:
            return {"list": []}
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        vid = _txt(ids[0]).strip()
        if not vid or not re.match(r"^\d+$", vid):
            return {"list": []}
        html = self._get(self.site_url + "/voddetail/{0}.html".format(vid))
        if not html:
            return {"list": []}

        title = u""
        m = re.search(r'<h1 class="entry-title">([\s\S]*?)</h1>', html)
        if m:
            title = _clean(m.group(1))
        if not title:
            m = re.search(r"<title>([\s\S]*?)</title>", html)
            if m:
                title = _clean(m.group(1)).split(u"_")[0].split(u"-")[0].strip()
        pic = self._parse_detail_pic(html)
        content = self._parse_detail_content(html, title)

        targets, names = self._parse_play_lines(html, title)
        if not targets:
            # 详情页未列出播放锚时的兜底：站点单集视频的播放地址固定为 {vid}-1-1
            targets = [(u"1", u"1", u"/vodplay/{0}-1-1.html".format(vid))]
        play_from, play_url = self._build_play(targets, names, vid)
        if not play_from:
            return {"list": []}

        return {"list": [{
            "vod_id": vid,
            "vod_name": title if title else u"未知片名",
            "vod_pic": pic if pic else self.default_pic,
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ========== 播放 ==========

    def playerContent(self, flag=None, id=None, vipFlags=None, *args, **kwargs):
        self._ensure()
        play_path = _txt(id)
        if u"$" in play_path:
            play_path = play_path.split(u"$")[-1]
        play_path = play_path.strip()
        if not play_path:
            return {"parse": 1, "url": u"", "header": self.headers}
        if u"/vodplay/" not in play_path and re.match(r"^\d+-\d+-\d+$", play_path):
            play_path = u"/vodplay/" + play_path + u".html"
        play_page = _abs(self.site_url, play_path)
        if u"/vodplay/" not in play_page:
            return {"parse": 1, "url": play_page, "header": self.headers}

        html = self._get(play_page, referer=play_page)
        data = _json_obj(html, u"player_aaaa")
        if not data:
            data = _json_obj(html, u"player_data")

        stream = u""
        if isinstance(data, dict):
            raw_url = _txt(data.get("url", u""))
            enc = data.get("encrypt", 1)
            try:
                enc = int(enc)
            except Exception:
                enc = 1
            if raw_url:
                if enc == 2:
                    stream = _b64decode(raw_url)
                elif "%" in raw_url:
                    stream = _unquote(raw_url)
                elif raw_url.startswith(u"http"):
                    stream = raw_url
                else:
                    stream = _unquote(raw_url) or _b64decode(raw_url)
            stream = stream.replace(u"\\/", u"/").replace(u"&amp;", u"&").strip()
            stream = _abs(self.site_url, stream)

        if not stream:
            # 该目标确无直链（站点给的空线路页）→ 交壳端按播放页自行嗅探，不冒充直链
            return {"parse": 1, "url": play_page, "header": self.headers}

        header = {
            "User-Agent": self.headers.get("User-Agent", ""),
            "Referer": self.site_url + "/",
        }
        if re.search(r"\.(m3u8|mp4|flv|ts)", stream, re.I):
            if self._probe_media(stream) is False:
                return {"parse": 1, "url": stream, "header": self.headers}
            return {"parse": 0, "url": stream, "header": header}
        return {"parse": 1, "url": stream, "header": self.headers}


# ========== 模块级转发（部分壳直接调模块函数） ==========

_inst = None


def _ins():
    global _inst
    if _inst is None:
        _inst = Spider()
        _inst.init("")
    return _inst


def getName():
    return _ins().getName()


def init(extend=""):
    return _ins().init(extend)


def getDependence():
    return _ins().getDependence()


def homeContent(filter=None):
    return _ins().homeContent(filter)


def homeVideoContent():
    return _ins().homeVideoContent()


def categoryContent(tid, pg=1, filter=None, extend=None):
    return _ins().categoryContent(tid, pg, filter, extend)


def detailContent(ids):
    return _ins().detailContent(ids)


def searchContent(key, quick=False, pg="1"):
    return _ins().searchContent(key, quick, pg)


def playerContent(flag="", id="", vipFlags=None):
    return _ins().playerContent(flag, id, vipFlags)


def localProxy(param=None):
    return _ins().localProxy(param)


def isVideoFormat(url):
    return _ins().isVideoFormat(url)


def manualVideoCheck():
    return _ins().manualVideoCheck()


def action(action=None):
    return _ins().action(action)


def destroy():
    return _ins().destroy()