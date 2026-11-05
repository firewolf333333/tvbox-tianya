# -*- coding: utf-8 -*-
# 仙女AV Python Spider | adult | py_18 | 2026-11-04
# 站点: MacCMS HTML 全链路, 播放页 player_aaaa -> m3u8 直链, 图片流后缀透传
import re, json, sys
try:
    import requests
except Exception:
    requests = None
import urllib.request
import gzip as _gzip
import posixpath
from urllib.parse import urlparse, urljoin, quote, unquote, parse_qsl

sys.path.append("..")
try:
    from base.spider import Spider as BaseSpider
except Exception:
    try:
        from base.spider import BaseSpider
    except Exception:
        BaseSpider = object

HOST = "https://qb7.xiannv.buzz"
UA = "Mozilla/5.0 (Linux; Android 14; 22127RK46C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.58 Mobile Safari/537.36"

class Spider(BaseSpider):
    def __init__(self):
        self.host = HOST
        self.headers = {"User-Agent": UA, "Referer": HOST + "/", "Accept-Encoding": "gzip, deflate", "Accept": "text/html,application/xhtml+xml"}
        self.hosts = [self.host]
        self.timeout = 15
        self.adf = M3U8AdFilter(spider=self, need_clean=True)
        self.classes = [
            {'type_id': '1', 'type_name': '中文传媒'},
            {'type_id': '2', 'type_name': '国产'},
            {'type_id': '3', 'type_name': '欧美AV'},
            {'type_id': '4', 'type_name': '日本AV'},
            {'type_id': '5', 'type_name': '明星网黄'},
            {'type_id': '21', 'type_name': '动漫'},
            {'type_id': '22', 'type_name': '吃瓜黑料'},
            {'type_id': '23', 'type_name': '变态暗网'},
            {'type_id': '24', 'type_name': '小众口味'},
            {'type_id': '25', 'type_name': 'AV解说'},
            {'type_id': '26', 'type_name': '短视频'},
            {'type_id': '27', 'type_name': 'AI换脸'},
            {'type_id': '28', 'type_name': '韩国AV'},
            {'type_id': '29', 'type_name': '吃瓜资讯'},
        ]

    def init(self, extend=""):
        return None

    def _fetch(self, url):
        # 通道1: 壳子 self.fetch（沙盒内最稳）
        sf = getattr(self, 'fetch', None)
        if callable(sf):
            try:
                r = sf(url, headers=self.headers, timeout=15)
                txt = ''
                if r is not None:
                    txt = getattr(r, 'content', None)
                    if isinstance(txt, bytes):
                        txt = txt.decode('utf-8', 'ignore')
                    else:
                        txt = getattr(r, 'text', '') or (txt if isinstance(txt, str) else '')
                if txt and len(txt) > 500:
                    return txt
            except Exception:
                pass
        # 通道2: requests 兜底 + 备用域
        tries = [url]
        for alt in getattr(self, 'hosts', []):
            if url.startswith(self.host) and alt != self.host:
                tries.append(alt + url[len(self.host):])
        # 通道3: urllib 标准库兜底（零第三方依赖）
        for u in tries:
            try:
                req = urllib.request.Request(u, headers=self.headers)
                resp = urllib.request.urlopen(req, timeout=getattr(self,'timeout',15))
                raw = resp.read()
                if resp.headers.get('Content-Encoding','') == 'gzip':
                    raw = _gzip.decompress(raw)
                txt = raw.decode('utf-8', 'ignore')
                if txt and len(txt) > 500:
                    return txt
            except Exception:
                continue
        if requests is None:
            return ""
        for u in tries:
            try:
                hh = dict(self.headers)
                hh['User-Agent'] = UA
                r = requests.get(u, headers=hh, timeout=getattr(self,'timeout',15))
                if r.status_code == 200 and len(r.text) > 500:
                    r.encoding = 'utf-8'
                    return r.text
            except Exception:
                continue
        return ""

    def _parse_cards(self, html):
        items = []
        pat = re.compile(r'<a\s+([^>]*?class="top-item[^"]*"[^>]*)>', re.S)
        anchors = list(pat.finditer(html))
        for idx, m in enumerate(anchors):
            attrs = m.group(1)
            mh = re.search(r'href="([^"]+)"', attrs)
            mt = re.search(r'title="([^"]+)"', attrs)
            if not mh or not mt:
                continue
            href = mh.group(1)
            name = mt.group(1).strip()
            vid_m = re.search(r'/id/([0-9]+)\.html', href)
            if not vid_m or not name:
                continue
            vid = vid_m.group(1)
            nxt = anchors[idx+1].start() if idx+1 < len(anchors) else min(len(html), m.start()+1500)
            block = html[m.end():nxt]
            im = re.search(r'background-image:\s*url\([\'"]?([^\'\")]+)', block)
            pic = im.group(1) if im else ""
            items.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": ""})
        return items

    def homeContent(self, filter):
        return {"class": self.classes, "filters": {}}

    def homeVideoContent(self):
        html = self._fetch(self.host + "/")
        return {"list": self._parse_cards(html)}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg)
        if pg <= 1:
            url = "%s/index.php/vod/type/id/%s.html" % (self.host, tid)
        else:
            url = "%s/index.php/vod/type/id/%s/page/%d.html" % (self.host, tid, pg)
        html = self._fetch(url)
        videos = self._parse_cards(html)
        return {"list": videos, "page": pg, "pagecount": 9999, "limit": len(videos), "total": 9999}

    def detailContent(self, array):
        vid = str(array[0])
        url = "%s/index.php/vod/detail/id/%s.html" % (self.host, vid)
        html = self._fetch(url)
        name = ""
        pic = ""
        m = re.search(r'<h2[^>]*>\s*片名：\s*([\s\S]*?)</h2>', html)
        if m:
            name = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not name:
            m = re.search(r'<title>([\s\S]*?)</title>', html)
            if m:
                name = m.group(1).strip()
        m = re.search(r"background-image:\s*url\(([^)]*)\)", html)
        if m:
            pic = m.group(1).strip().strip(chr(39)).strip(chr(34))
        play_url = ""
        pm = re.findall(r'href="(/index\.php/vod/play/id/' + re.escape(vid) + r'/sid/[0-9]+/nid/[0-9]+\.html)"', html)
        if pm:
            play_url = "正片$" + pm[0]
        vod = {"vod_id": vid, "vod_name": name or vid, "vod_pic": pic, "vod_content": "",
               "vod_play_from": "ckm3u8" if play_url else "", "vod_play_url": play_url}
        return {"list": [vod]}

    def searchContent(self, key, quick, pg=1):
        from urllib.parse import quote
        url = "%s/index.php/vod/search.html?wd=%s" % (self.host, quote(key))
        html = self._fetch(url)
        return {"list": self._parse_cards(html)}

    def playerContent(self, flag, id, vipFlags):
        url = ""
        if id.startswith("/"):
            url = self.host + id
        elif id.startswith("http"):
            url = id
        else:
            url = "%s/index.php/vod/play/id/%s.html" % (self.host, id)
        html = self._fetch(url)
        m = re.search(r'player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', html)
        if not m:
            return {"parse": 1, "playUrl": "", "url": url, "header": {"User-Agent": UA}}
        raw = m.group(1).replace("\\/", "/")
        try:
            play = json.loads(raw).get("url") or ""
        except Exception:
            mm = re.search(r'"url"\s*:\s*"([^"]+)"', raw)
            play = mm.group(1).replace("\\/", "/") if mm else ""
        if not play:
            return {"parse": 1, "playUrl": "", "url": url, "header": {"User-Agent": UA}}
        if '.m3u8' in play.lower() and getattr(self, 'adf', None) and self.adf.need_clean:
            play = self.adf.proxy_url(play)
        return {"parse": 0, "playUrl": "", "url": play, "header": {"User-Agent": UA}}

    def localProxy(self, param):
        return self.adf.local_proxy(param)

    def recommendContent(self, tid, pg):
        return self.categoryContent(tid, pg, False, {})

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)



IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.avif')
VIDEO_EXT = ('.ts', '.m4s', '.mp4', '.aac', '.m4a', '.cmfv', '.cmfa', '.m4v')
_GLOBAL_TAGS = (
    '#EXTM3U', '#EXT-X-VERSION', '#EXT-X-TARGETDURATION', '#EXT-X-MEDIA-SEQUENCE',
    '#EXT-X-DISCONTINUITY-SEQUENCE', '#EXT-X-PLAYLIST-TYPE', '#EXT-X-INDEPENDENT-SEGMENTS',
    '#EXT-X-START', '#EXT-X-I-FRAMES-ONLY',
)

class M3U8AdFilter(object):
    """m3u8 广告分片过滤器。spider 只需提供 getProxyUrl() 与 fetch()。"""

    def __init__(self, spider=None, need_clean=True, ad_dirs=None, anchor_dirs=None,
                 min_coverage=0.30, long_factor=3.0, long_floor=25.0,
                 max_depth=2, logger=None):
        self.spider = spider
        self.need_clean = bool(need_clean)
        # 已知广告目录 / 已知正片目录（都可为空，留空则动态推导）
        self.ad_dirs = [self._norm_dir(d) for d in (ad_dirs or []) if d]
        self.anchor_dirs = [self._norm_dir(d) for d in (anchor_dirs or []) if d]
        self.min_coverage = float(min_coverage)   # 目录覆盖率门槛
        self.long_factor = float(long_factor)     # 长片判据倍数
        self.long_floor = float(long_floor)       # 长片判据秒数下限
        self.max_depth = int(max_depth)           # 主表/子表递归上限
        self.logger = logger

    # ================= 接入适配层 =================
    def _log(self, data):
        if self.logger:
            try:
                self.logger(data)
            except Exception:
                pass

    def _proxy_base(self):
        sp = self.spider
        if sp is None:
            return ''
        for name in ('getProxyUrl', 'get_proxy_url'):
            fn = getattr(sp, name, None)
            if callable(fn):
                try:
                    return str(fn() or '')
                except Exception:
                    return ''
        return ''

    def _fetch(self, url, timeout=20, referer=None):
        sp = self.spider
        if sp is None:
            return b''
        headers = {}
        for name in ('headers', '_headers'):
            h = getattr(sp, name, None)
            if isinstance(h, dict):
                headers.update(h)
                break
        if referer:
            headers.setdefault('Referer', referer)
        fn = getattr(sp, 'fetch', None)
        if callable(fn):
            try:
                resp = fn(url, headers=headers, timeout=timeout)
                if resp is not None:
                    content = getattr(resp, 'content', None)
                    if content is None:
                        content = getattr(resp, 'text', b'')
                    if isinstance(content, str):
                        content = content.encode('utf-8', 'ignore')
                    if content:
                        return content
            except Exception:
                pass
        sf = getattr(sp, '_fetch', None)
        if callable(sf):
            try:
                t = sf(url)
                if t and isinstance(t, str):
                    return t.encode('utf-8', 'ignore')
            except Exception:
                pass
        if requests is not None:
            try:
                hh = headers or {'User-Agent': UA}
                rr = requests.get(url, headers=hh, timeout=timeout)
                if rr.status_code == 200:
                    return rr.content
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=timeout)
            raw = resp.read()
            if resp.headers.get('Content-Encoding','') == 'gzip':
                raw = _gzip.decompress(raw)
            return raw
        except Exception:
            pass
        return b''

    # ================= 工具 =================
    @staticmethod
    def _norm_dir(d):
        d = str(d or '').strip()
        if not d:
            return ''
        return d if d.endswith('/') else d + '/'

    @staticmethod
    def _path(url, source_url):
        u = url if url.startswith(('http://', 'https://')) else urljoin(source_url, url)
        return urlparse(u).path

    @staticmethod
    def _parse_duration(line):
        m = re.match(r'#EXTINF:\s*([\d.]+)', line or '')
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def proxy_url(self, url, depth=0):
        """生成代理地址。已编码字符不再二次编码，避免签名 URL 失效。"""
        u = str(url or '').strip().replace('\\/', '/')
        base = self._proxy_base()
        if not base:
            return u
        sep = '&' if '?' in base else '?'
        parts = []
        if 'do=py' not in base:
            parts.append('do=py')
        parts.append('url=' + quote(u, safe=''))
        if depth:
            parts.append('d=%d' % int(depth))
        return base + sep + '&'.join(parts)

    # ================= 取证（第 0 步）=================
    def probe(self, text, source_url):
        """不上代理也能先看清结构：返回证据 dict，据此决定 need_clean。"""
        lines = self._lines(text)
        evidence = {
            'segment_count': 0, 'is_multi_bitrate': False, 'is_fake_image_stream': False,
            'dirs': {}, 'key_uris': [], 'suspicious_ad_dirs': [], 'anchor_dirs': [],
            'dur_median': None, 'cue_segments': 0,
        }
        if any(l.startswith('#EXT-X-STREAM-INF') for l in lines):
            evidence['is_multi_bitrate'] = True
            evidence['sub_streams'] = [l for l in lines if not l.startswith('#') and '.m3u8' in l.lower()]
        pre, entries, _ = self._split(lines)
        evidence['segment_count'] = len(entries)
        if not entries:
            return evidence

        counter = self._dir_counter(entries, source_url)
        evidence['dirs'] = dict(sorted(counter.items(), key=lambda kv: -kv[1]))
        total = len(entries) or 1
        evidence['is_fake_image_stream'] = self._is_image_stream(entries, source_url)
        evidence['key_uris'] = [self._tag_uri(t) for t in pre + [x for e in entries for x in e['tags']]
                                if t.startswith(('#EXT-X-KEY', '#EXT-X-MAP')) and 'URI=' in t]
        evidence['cue_segments'] = sum(1 for e in entries if e.get('cue'))
        anchors, strength = self._resolve_anchors(entries, source_url, evidence['is_fake_image_stream'], pre)
        evidence['anchor_dirs'] = anchors
        evidence['anchor_strength'] = strength
        evidence['suspicious_ad_dirs'] = [d for d, c in counter.items()
                                          if d not in anchors and not any(d.startswith(a) for a in anchors)]
        durs = sorted(e['dur'] for e in entries
                      if e.get('dur') and any(self._path(e['url'], source_url).startswith(a) for a in anchors))
        evidence['dur_median'] = durs[len(durs) // 2] if durs else None
        evidence['need_clean'] = bool(evidence['suspicious_ad_dirs'] or evidence['is_fake_image_stream']
                                      or evidence['cue_segments'])
        return evidence

    @staticmethod
    def _tag_uri(tag):
        m = re.search(r'URI="([^"]+)"', tag or '')
        return m.group(1) if m else ''

    # ================= 解析 =================
    @staticmethod
    def _lines(text):
        return [l.strip() for l in str(text or '').replace('\r', '').split('\n') if l.strip()]

    def _split(self, lines):
        """拆成 (头部全局标签, 分片条目, 尾部标签)。

        关键点：分片之间出现的标签（KEY / MAP / DISCONTINUITY / CUE）属于**下一条**分片，
        不能丢到尾部，否则中途换 KEY 的流会整段解不开。
        """
        pre, entries, pending = [], [], []
        cur_inf, cur_tags = None, []
        cue_on = False
        seen_entry = False

        for line in lines:
            if line.startswith('#'):
                if line.startswith('#EXTINF'):
                    if cur_inf is not None:          # 缺媒体行的残条，丢弃
                        cur_inf, cur_tags = None, []
                    cur_inf = line
                    continue
                if cur_inf is not None:              # EXTINF 之后的标签归本条分片
                    cur_tags.append(line)
                elif seen_entry:                     # 分片之间的标签归下一条分片
                    pending.append(line)
                else:                                # 首个 EXTINF 之前：全局头
                    pre.append(line)
                if line.startswith('#EXT-X-CUE-OUT'):
                    cue_on = True
                elif line.startswith('#EXT-X-CUE-IN'):
                    cue_on = False
                continue

            # 媒体行
            if cur_inf is None:
                pre.append(line)                     # 少见的伪 m3u：无 EXTINF 的裸地址
                continue
            entries.append({'dur': self._parse_duration(cur_inf), 'inf': cur_inf,
                            'tags': pending + cur_tags, 'url': line, 'cue': cue_on})
            seen_entry = True
            pending, cur_inf, cur_tags = [], None, []

        trailer = pending + cur_tags
        # cue 标记过半时不可信，整体作废（防止把正片当广告区间）
        if entries:
            cue_n = sum(1 for e in entries if e['cue'])
            if cue_n * 2 >= len(entries):
                for e in entries:
                    e['cue'] = False
        return pre, entries, trailer

    def _dir_counter(self, entries, source_url):
        counter = {}
        for e in entries:
            d = posixpath.dirname(self._path(e['url'], source_url))
            if d and d != '/':
                d += '/'
                counter[d] = counter.get(d, 0) + 1
        return counter

    def _is_image_stream(self, entries, source_url):
        """强证据：有图片后缀分片且无视频后缀分片。不做域名特征猜测。"""
        has_video = has_image = False
        for e in entries:
            p = self._path(e['url'], source_url).lower()
            if p.endswith(VIDEO_EXT):
                has_video = True
            elif p.endswith(IMAGE_EXT):
                has_image = True
        return has_image and not has_video

    def _resolve_anchors(self, entries, source_url, is_img, pre=None):
        """返回 (锚点目录列表, 强度)。强度: config/key/dir/weak/none"""
        if self.anchor_dirs:
            return self.anchor_dirs, 'config'
        if not entries:
            return [], 'none'
        total = len(entries)
        counter = self._dir_counter(entries, source_url)
        if not counter:
            return [], 'none'

        # 强锚点：KEY / MAP 目录。多条 KEY 时取覆盖分片最多的那条，
        # 否则广告段自带的 KEY 目录会被误当成锚点（把广告一起放行）。
        key_dirs = []
        tags_all = list(pre or []) + [t for e in entries for t in e['tags']]
        for t in tags_all:
            if t.startswith(('#EXT-X-KEY', '#EXT-X-MAP')) and 'URI=' in t:
                kp = self._path(self._tag_uri(t), source_url)
                kd = posixpath.dirname(kp)
                if kd and kd != '/':
                    key_dirs.append(kd + '/')
        if key_dirs:
            best, best_n = None, 0
            for kd in sorted(set(key_dirs)):
                n = sum(1 for e in entries if self._path(e['url'], source_url).startswith(kd))
                if n > best_n:
                    best, best_n = kd, n
            if best:
                return [best], 'key'

        # 覆盖率锚点：以占比最高的目录为主锚点，
        # 同层数量不低于主目录一半的（分库正片）以及其子/父目录一并纳入。
        # 广告目录通常只占零头，不会进来；万一进来也是漏广告，不会误杀。
        top = max(counter.items(), key=lambda kv: kv[1])[0]
        topn = counter[top]
        anchors = [top]
        for d, c in counter.items():
            if d == top:
                continue
            if c * 2 > topn or d.startswith(top) or top.startswith(d):
                anchors.append(d)
        if anchors == [top] and topn * 2 < total:
            # 主目录都不到一半 -> 结构太散，退化为弱锚点
            return sorted(set(anchors)), 'weak'
        return sorted(set(anchors)), 'dir'

    # ================= 主入口 =================
    def clean(self, text, source_url, depth=0):
        lines = self._lines(text)
        if not lines:
            return '#EXTM3U\n'

        # 主表：子流改代理地址，音轨 / I-FRAME 的 URI 也要处理
        if any(l.startswith('#EXT-X-STREAM-INF') for l in lines):
            return self._rewrite_master(lines, source_url, depth)

        pre, entries, trailer = self._split(lines)
        if not entries:
            return '\n'.join(self._rewrite_tag(l, source_url) for l in lines) + '\n'

        is_img = self._is_image_stream(entries, source_url)
        anchors, strength = self._resolve_anchors(entries, source_url, is_img, pre)
        check = {'url': lambda u: self._path(u, source_url)}
        ctx = {'ad_dirs': self.ad_dirs, 'anchors': anchors, 'median': None,
               'path': check['url']}

        # 时长基线：只统计锚点内分片
        durs = sorted(e['dur'] for e in entries
                      if e.get('dur') and (not anchors or any(check['url'](e['url']).startswith(a) for a in anchors)))
        ctx['median'] = durs[len(durs) // 2] if durs else None

        last_idx = len(entries) - 1
        reasons, kept = {}, []
        for i, e in enumerate(entries):
            r = self._decide(e, ctx, i == last_idx)
            if r:
                reasons[r] = reasons.get(r, 0) + 1
            else:
                kept.append(e)

        removed = len(entries) - len(kept)

        # 误杀保护：一条不留、或滤掉一半以上 -> 整体回退
        if removed:
            suspicious = (not kept) or (removed * 2 >= len(entries))
            if suspicious:
                self._log({'stage': 'clean', 'fallback': 'no_filter', 'removed': removed,
                           'kept': len(kept), 'anchor': anchors, 'strength': strength,
                           'reasons': reasons})
                return '\n'.join(self._rewrite_tag(l, source_url) for l in lines) + '\n'
            self._log({'stage': 'clean', 'removed': removed, 'kept': len(kept),
                       'anchor': anchors, 'strength': strength, 'image': is_img,
                       'reasons': reasons})

        out = [t for t in pre if t.split(':')[0] in _GLOBAL_TAGS]
        if not out or out[0] != '#EXTM3U':
            out.insert(0, '#EXTM3U')

        cur_key, cur_map = self._initial_state(pre)
        emit_key, emit_map = None, None
        for e in entries:
            k, m = self._scan_state(e['tags'])
            if k is not None:
                cur_key = k
            if m is not None:
                cur_map = m
            if e not in kept:
                continue                                  # 状态照样更新，只是不输出
            if cur_key and cur_key != emit_key:
                out.extend(self._rewrite_tag(t, source_url) for t in cur_key)
                emit_key = cur_key
            if cur_map and cur_map != emit_map:
                out.append(self._rewrite_tag(cur_map, source_url))
                emit_map = cur_map
            out.append(e['inf'])
            out.extend(self._rewrite_tag(t, source_url) for t in e['tags']
                       if not t.startswith(('#EXT-X-KEY', '#EXT-X-MAP',
                                            '#EXT-X-CUE-', '#EXT-X-SCTE35')))
            out.append(e['url'] if e['url'].startswith(('http://', 'https://'))
                       else urljoin(source_url, e['url']))

        for t in trailer:
            if t.startswith(_GLOBAL_TAGS):
                out.append(self._rewrite_tag(t, source_url))
        if not any(t.startswith('#EXT-X-ENDLIST') for t in out) and any(
                t.startswith('#EXT-X-ENDLIST') for t in lines):
            out.append('#EXT-X-ENDLIST')

        return '\n'.join(self._dedup(out)) + '\n'

    def _decide(self, e, ctx, is_last):
        if e.get('cue'):
            return 'cue'
        p = ctx['path'](e['url'])
        if self.ad_dirs and any(p.startswith(d) for d in self.ad_dirs):
            return 'ad_dir'
        if ctx['anchors'] and not any(p.startswith(a) for a in ctx['anchors']):
            return 'off_anchor'
        dur, median = e.get('dur'), ctx.get('median')
        if median and dur is not None and not is_last:
            if dur > max(median * self.long_factor, self.long_floor):
                return 'long'
            if dur < min(2.0, median * 0.25):
                return 'short'
        return None

    @staticmethod
    def _scan_state(tags):
        key, mp = None, None
        for t in tags:
            if t.startswith('#EXT-X-KEY'):
                if key is None:
                    key = [t]
                else:
                    key.append(t)
            elif t.startswith('#EXT-X-MAP'):
                mp = t
        return key, mp

    @staticmethod
    def _initial_state(pre):
        key_lines, mp = [], None
        for t in pre:
            if t.startswith('#EXT-X-KEY'):
                if not key_lines or not key_lines[-1].startswith('#EXT-X-KEY'):
                    key_lines = [t]
                else:
                    key_lines.append(t)
            elif t.startswith('#EXT-X-MAP'):
                mp = t
        return (key_lines or None), mp

    def _rewrite_master(self, lines, source_url, depth):
        out = []
        for line in lines:
            if line.startswith('#'):
                if 'URI="' in line:
                    def repl(m):
                        uri = m.group(1)
                        full = uri if uri.startswith(('http://', 'https://')) else urljoin(source_url, uri)
                        if '.m3u8' in full.lower() and depth < self.max_depth:
                            return 'URI="' + self.proxy_url(full, depth + 1) + '"'
                        return 'URI="' + full + '"'
                    line = re.sub(r'URI="([^"]+)"', repl, line)
                out.append(line)
                continue
            child = line if line.startswith(('http://', 'https://')) else urljoin(source_url, line)
            if '.m3u8' in child.lower() and depth < self.max_depth:
                out.append(self.proxy_url(child, depth + 1))
            else:
                out.append(child)
        return '\n'.join(out) + '\n'

    def _rewrite_tag(self, line, source_url):
        if 'URI="' in line:
            def repl(m):
                uri = m.group(1)
                if uri.startswith(('http://', 'https://')):
                    return 'URI="' + uri + '"'
                return 'URI="' + urljoin(source_url, uri) + '"'
            return re.sub(r'URI="([^"]+)"', repl, line)
        if line and not line.startswith('#'):
            return line if line.startswith(('http://', 'https://')) else urljoin(source_url, line)
        return line

    @staticmethod
    def _dedup(lines):
        """清孤立噪声：连续 DISCONTINUITY、METHOD=NONE、断层 PDT。"""
        noise = ('#EXT-X-DISCONTINUITY', '#EXT-X-KEY:METHOD=NONE')
        out = []
        for i, line in enumerate(lines):
            if line in noise:
                prev = out[-1] if out else ''
                nxt = lines[i + 1] if i + 1 < len(lines) else ''
                if prev in noise or not nxt or nxt.startswith('#EXT-X-ENDLIST'):
                    continue
            out.append(line)
        while len(out) > 1 and out[-1] in noise:
            out.pop()
        return out

    # ================= localProxy =================
    def local_proxy(self, param):
        try:
            target, depth = self._parse_param(param)
            if not target or not re.match(r'^https?://', target, re.I):
                return [400, 'text/plain', 'invalid url']
            content = self._fetch(target, timeout=20)
            if not content:
                # 二次尝试：带 Referer 再拉一次（不少 CDN 首次裸拉 403）
                p = urlparse(target)
                content = self._fetch(target, timeout=20, referer=p.scheme + '://' + p.netloc + '/')
            if not content:
                return [502, 'text/plain', 'fetch failed']
            head = content[:1024].lstrip(b'\xef\xbb\xbf').lstrip()
            if not head.startswith(b'#EXTM3U'):
                # 不是 m3u8（key / 分片等）原样透传，不碰内容
                return [200, 'application/octet-stream', content]
            text = content.decode('utf-8', 'ignore')
            return [200, 'application/vnd.apple.mpegurl', self.clean(text, target, depth).encode('utf-8')]
        except Exception as e:
            self._log({'stage': 'localProxy', 'error': type(e).__name__})
            return [500, 'text/plain', 'proxy error']

    @staticmethod
    def _parse_param(param):
        raw = {}
        if isinstance(param, dict):
            raw = dict(param)
        else:
            s = str(param or '').lstrip('?')
            for kv in s.split('&'):
                if '=' in kv:
                    k, v = kv.split('=', 1)
                    raw[k] = v
        target = raw.get('url') or raw.get('source') or ''
        if isinstance(target, str) and '%' in target:
            target = unquote(target)             # 只解一次
        depth = 0
        try:
            depth = int(raw.get('d') or 0)
        except Exception:
            depth = 0
        return target, depth
