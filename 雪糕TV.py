import re, json
try:
    import requests as _requests
except Exception:
    _requests = None


class Spider:
    def __init__(self):
        self.site = "https://www.xgitv.com"
        self.name = "雪糕TV"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.site,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.s = self.session = self.sess = _requests.Session() if _requests else None
        self._extend = {}
        self._home = None
        self._cats = [("dianying", "电影"), ("dianshiju", "剧集"), ("zongyi", "综艺"), ("dongman", "动漫")]
        self._subs = {
            "dianying": [("zilei1", "动作片"), ("zilei2", "喜剧片"), ("zilei3", "爱情片"), ("zilei4", "科幻片"), ("zilei5", "恐怖片"), ("zilei6", "剧情片"), ("zilei7", "战争片"), ("jilupian", "纪录片"), ("qita", "其他")],
            "dianshiju": [("zilei8", "国产剧"), ("zilei9", "港台剧"), ("zilei10", "日韩剧"), ("zilei11", "欧美剧"), ("haiwaiju", "海外剧")],
            "zongyi": [],
            "dongman": [],
        }

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u

    def destroy(self):
        pass

    def action(self, action):
        return {}

    def _get(self, url, referer=None):
        h = dict(self.header)
        if referer:
            h["Referer"] = referer
        if self.s is not None:
            try:
                r = self.s.get(url, headers=h, timeout=15, allow_redirects=True)
                if r.status_code < 400:
                    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                        r.encoding = "utf-8"
                    return r.text
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception:
            return ""

    def _u(self, u):
        if not u:
            return u
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            m = re.match(r"(https?://[^/]+)", self.site)
            return (m.group(1) if m else self.site) + u
        return self.site.rstrip("/") + "/" + u.lstrip("/")

    def _clean(self, s):
        if not s:
            return ""
        import html as _h
        s = re.sub(r"<[^>]+>", "", s)
        return _h.unescape(s).strip()

    def _json_obj(self, html, key):
        i = html.find(key)
        if i < 0:
            return None
        j = html.find("{", i)
        if j < 0:
            return None
        depth = 0
        instr = False
        esc = False
        k = j
        while k < len(html):
            c = html[k]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            else:
                if c == '"':
                    instr = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(html[j:k + 1])
                        except Exception:
                            return None
            k += 1
        return None

    def _items(self, html):
        out = []
        seen = set()
        for bm in re.finditer(r'<li[^>]*class="[^"]*hl-list-item[^"]*"[^>]*>([\s\S]*?)</li>', html):
            block = bm.group(1)
            hm = re.search(r'href="(/voddetail/\d+\.html[^"]*)"', block)
            if not hm:
                continue
            vid = self._u(hm.group(1))
            if vid in seen:
                continue
            tm = re.search(r'title="([^"]+)"', block)
            if not tm:
                continue
            im = re.search(r'data-original="([^"]+)"', block) or re.search(r'<img[^>]+src="([^"]+)"', block)
            rm = re.search(r'remarks">([^<]+)</span>', block)
            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": self._clean(tm.group(1)),
                "vod_pic": self._u(im.group(1)) if im else "",
                "vod_remarks": self._clean(rm.group(1)) if rm else "",
            })
        return out

    def _banner_items(self, html):
        out = []
        seen = set()
        for bm in re.finditer(r'<a[^>]*class="[^"]*hl-br-thumb[^"]*"[^>]*href="(/voddetail/\d+\.html[^"]*)"[^>]*title="([^"]+)"[^>]*data-original="([^"]+)"', html):
            vid = self._u(bm.group(1))
            if vid in seen:
                continue
            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": self._clean(bm.group(2)),
                "vod_pic": self._u(bm.group(3)),
                "vod_remarks": "",
            })
        return out

    def _pagecount(self, html):
        m = re.search(r'hl-page-total">\s*\d+\s*&nbsp;/&nbsp;\s*(\d+)\s*页', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return 1

    def _resolve(self, tid, extend):
        tid = str(tid or "")
        m = re.search(r"/vodshow/([a-z0-9]+)", tid)
        if m:
            tid = m.group(1)
        if tid not in self._subs:
            return "dianying"
        sub = ""
        e = extend
        if isinstance(e, str) and e.strip():
            try:
                e = json.loads(e)
            except Exception:
                e = {}
        if isinstance(e, dict):
            sub = str(e.get("sub", "") or "")
        if sub:
            for s, _ in self._subs.get(tid, []):
                if s == sub:
                    return sub
        return tid

    def _filters(self):
        filters = {}
        for slug, name in self._cats:
            vals = [{"n": "全部", "v": ""}]
            for s, n in self._subs.get(slug, []):
                vals.append({"n": n, "v": s})
            filters[slug] = [{"key": "sub", "name": "分类", "value": vals}]
        return filters

    def init(self, extend=""):
        self._extend = {}
        if isinstance(extend, dict):
            self._extend = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                e = json.loads(extend)
                if isinstance(e, dict):
                    self._extend = e
            except Exception:
                pass

    def homeContent(self, filter=None):
        if self._home is None:
            self._home = self._get(self.site)
        html = self._home or ""
        cats = [{"type_id": s, "type_name": n} for s, n in self._cats]
        items = self._items(html)
        seen = {i["vod_id"] for i in items}
        for b in self._banner_items(html):
            if b["vod_id"] not in seen:
                seen.add(b["vod_id"])
                items.append(b)
        return {"class": cats, "filters": self._filters(), "list": items}

    def homeVideoContent(self):
        if self._home is None:
            self._home = self._get(self.site)
        html = self._home or ""
        items = self._items(html)
        seen = {i["vod_id"] for i in items}
        for b in self._banner_items(html):
            if b["vod_id"] not in seen:
                seen.add(b["vod_id"])
                items.append(b)
        return {"list": items}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        slug = self._resolve(tid, extend if extend is not None else self._extend)
        url = self.site + "/vodshow/" + slug + "--------" + str(pg) + "---.html"
        html = self._get(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 36, "total": pg * 36}
        items = self._items(html)
        pc = self._pagecount(html)
        if pc < pg:
            pc = pg
        return {"list": items, "page": pg, "pagecount": pc, "limit": 36, "total": pc * 36}

    def detailContent(self, ids):
        vid = ids
        if isinstance(ids, (list, tuple)):
            vid = ids[0] if ids else ""
        vid = str(vid or "").strip()
        if not vid:
            return {"list": []}
        if vid.startswith("http"):
            url = vid
        elif vid.startswith("/"):
            url = self._u(vid)
        elif vid.isdigit():
            url = self.site + "/voddetail/" + vid + ".html"
        else:
            m = re.search(r"(\d+)", vid)
            if not m:
                return {"list": []}
            url = self.site + "/voddetail/" + m.group(1) + ".html"
        html = self._get(url)
        if not html or "hl-dc-title" not in html:
            return {"list": []}
        tm = re.search(r'<h2[^>]*class="[^"]*hl-dc-title[^"]*"[^>]*>(.*?)</h2>', html, re.S)
        title = self._clean(tm.group(1)) if tm else ""
        if not title:
            tm2 = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
            if tm2:
                t2 = self._clean(tm2.group(1))
                m2 = re.search(r"《([^》]+)》", t2)
                title = m2.group(1) if m2 else t2.split("_")[0].split("在")[0]
        pm = re.search(r'<div[^>]*class="[^"]*hl-dc-pic[^"]*"[^>]*>[\s\S]*?data-original="([^"]+)"', html)
        pic = self._u(pm.group(1)) if pm else ""
        actor = ""
        am = re.search(r'<em[^>]*>主演：</em>(.*?)</li>', html, re.S)
        if am:
            actor = self._clean(am.group(1)).replace("/", " ")
            actor = re.sub(r"\s+", " ", actor)
        director = ""
        dm2 = re.search(r'<em[^>]*>导演：</em>(.*?)</li>', html, re.S)
        if dm2:
            director = self._clean(dm2.group(1)).replace("/", " ")
        remarks = ""
        sm = re.search(r'<em[^>]*>状态：</em>(.*?)</li>', html, re.S)
        if sm:
            remarks = self._clean(sm.group(1))
        desc = ""
        cm = re.search(r'<span[^>]*class="[^"]*hl-content-text[^"]*"[^>]*>(.*?)</span>', html, re.S)
        if cm:
            desc = self._clean(cm.group(1))
        tabs = re.findall(r'hl-tabs-btn[^>]*alt="([^"]+)"', html)
        boxes = re.findall(r'<ul[^>]*class="[^"]*hl-plays-list[^"]*"[^>]*>(.*?)</ul>', html, re.S)
        play_from = []
        play_url = []
        for idx, box in enumerate(boxes):
            name = tabs[idx] if idx < len(tabs) else "线路%d" % (idx + 1)
            eps = []
            seen = set()
            for em in re.finditer(r'href="(/vodplay/\d+-\d+-\d+\.html)"[^>]*>([^<]*)</a>', box, re.S):
                href, ename = em.group(1), self._clean(em.group(2))
                if href in seen:
                    continue
                seen.add(href)
                if not ename:
                    ename = "第%d集" % (len(eps) + 1)
                eps.append("%s$%s" % (ename, self._u(href)))
            if eps:
                play_from.append(name)
                play_url.append("#".join(eps))
        vod = {
            "vod_id": url,
            "vod_name": title,
            "vod_pic": pic,
            "vod_actor": actor,
            "vod_director": director,
            "vod_remarks": remarks,
            "vod_content": desc,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        if not key:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 12, "total": pg * 12}
        from urllib.parse import quote
        k = quote(str(key))
        if pg <= 1:
            url = self.site + "/vodsearch/-------------.html?wd=" + k
        else:
            url = self.site + "/vodsearch/" + k + "----------" + str(pg) + "---.html"
        html = self._get(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 12, "total": pg * 12}
        items = self._items(html)
        pc = self._pagecount(html)
        if pc < pg:
            pc = pg
        return {"list": items, "page": pg, "pagecount": pc, "limit": 12, "total": pc * 12}

    def playerContent(self, flag, ids, vipFlags=None):
        url = ids
        if isinstance(ids, (list, tuple)):
            url = ids[0] if ids else ""
        url = str(url or "").strip()
        if not url:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        if not url.startswith("http"):
            url = self._u(url)
        u = url.lower()
        if u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u:
            return {"parse": 0, "url": url, "header": dict(self.header)}
        html = self._get(url, referer=self.site)
        if not html:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        found = ""
        d = self._json_obj(html, "player_aaaa")
        if d and d.get("url"):
            found = d["url"]
        if not found:
            m = re.search(r'var\s+player_aaaa\s*=\s*\{[^}]*?"url"\s*:\s*"([^"]+)"', html)
            if m:
                found = m.group(1)
        if not found:
            m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
            if m:
                found = m.group(1)
        if not found:
            im = re.search(r'<iframe[^>]+src="([^"]+)"', html)
            if im:
                return self.playerContent(flag, self._u(im.group(1)), vipFlags)
        if not found:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        from urllib.parse import unquote
        found = unquote(found.strip())
        if found.startswith("//"):
            found = "https:" + found
        elif not found.startswith("http"):
            found = self._u(found)
        return {"parse": 0, "url": found, "header": dict(self.header)}

    def localProxy(self, param):
        u = param.get("url", "") if isinstance(param, dict) else ""
        if not u:
            return [403, "text/plain", b"", None]
        h = dict(self.header)
        if self.s is not None:
            try:
                r = self.s.get(u, headers=h, timeout=15)
                return [200, r.headers.get("Content-Type", "application/octet-stream"), r.content, None]
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(u, headers=h)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return [200, resp.headers.get("Content-Type", "application/octet-stream"), resp.read(), None]
        except Exception:
            return [403, "text/plain", b"", None]
