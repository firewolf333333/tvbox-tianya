# -*- coding: utf-8 -*-
"""
青花瓷影视 https://m.cj1nym.com/  狼壳(TVBox) 单条导入 py 源
"""

import sys
import json
import time
import uuid
import gzip
import ssl
import hashlib
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

HOST = "https://m.cj1nym.com"
API = HOST + "/api/mw-movie"
SIGN_KEY = "cb808529bae6b6be45ecfab29a4889bc"
UA = ("Mozilla/5.0 (Linux; Android 13; NX789J) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

REQ_TIMEOUT = 8
OK_TTL = 300
BAD_TTL = 60
PAGE_SIZE = 36


class Spider(_BaseSpider):

    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self._uuid = str(uuid.uuid4())
        self._cache = {}

    def getName(self):
        return "青花瓷影视"

    def init(self, extend=""):
        return

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return (".m3u8" in u) or (".mp4" in u)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._cache = {}

    def _cache_get(self, key):
        hit = self._cache.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > (OK_TTL if val else BAD_TTL):
            self._cache.pop(key, None)
            return None
        return val

    def _cache_set(self, key, val):
        self._cache[key] = (time.time(), val)

    def _sign_headers(self, path, params):
        data = {}
        for k, v in (params or {}).items():
            if v is None or isinstance(v, (list, dict, tuple)) or v == "":
                continue
            data[k] = v
        ts = str(int(time.time() * 1000))
        raw = "key=" + SIGN_KEY + "&t=" + ts
        if data:
            part = "&".join("%s=%s" % (k, data[k]) for k in sorted(data.keys()))
            raw = part + "&" + raw
        md5hex = hashlib.md5(raw.encode("utf-8")).hexdigest()
        sign = hashlib.sha1(md5hex.encode("utf-8")).hexdigest()
        return {
            "client-type": "3",
            "sign": sign,
            "t": ts,
            "deviceId": self._uuid,
            "authorization": "",
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
        }

    def _open(self, url, headers):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers or {})
        resp = urllib.request.urlopen(req, timeout=REQ_TIMEOUT, context=ctx)
        raw = resp.read()
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return raw

    def _fetch(self, path, params=None, ttl=None):
        key = (path, json.dumps(params or {}, sort_keys=True, ensure_ascii=False))
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        url = API + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        out = None
        try:
            raw = self._open(url, self._sign_headers(path, params))
            body = json.loads(raw.decode("utf-8", "replace"))
            if isinstance(body, dict) and body.get("code") == 200:
                out = body.get("data")
        except Exception:
            out = None
        self._cache_set(key, out)
        return out

    def _mk_item(self, it):
        return {
            "vod_id": str(it.get("vodId") or ""),
            "vod_name": str(it.get("vodName") or ""),
            "vod_pic": str(it.get("vodPic") or ""),
            "vod_remarks": str(it.get("vodRemarks") or it.get("vodVersion") or ""),
        }

    def _collect(self, obj, out=None, seen=None):
        if out is None:
            out, seen = [], set()
        if isinstance(obj, dict):
            vid = obj.get("vodId")
            name = obj.get("vodName")
            if vid is not None and name:
                if vid not in seen:
                    seen.add(vid)
                    out.append(self._mk_item(obj))
            else:
                for v in obj.values():
                    self._collect(v, out, seen)
        elif isinstance(obj, list):
            for v in obj:
                self._collect(v, out, seen)
        return out

    def _norm_list(self, lst):
        out = []
        for it in (lst or []):
            if isinstance(it, dict) and it.get("vodId") is not None:
                out.append(self._mk_item(it))
        return out

    def _paged(self, data, pg):
        if not isinstance(data, dict):
            return None, None, None
        lst = data.get("list")
        if isinstance(lst, list):
            lst = self._norm_list(lst)
        else:
            lst = self._collect(data)
        total = data.get("totalCount")
        pages = data.get("totalPage")
        try:
            pages = int(pages)
        except Exception:
            pages = None
        try:
            total = int(total)
        except Exception:
            total = None
        return lst, pages, total

    def homeContent(self, filter=False):
        classes = []
        cats = self._fetch("/anonymous/get/filer/type")
        if isinstance(cats, list):
            for c in cats:
                if not isinstance(c, dict) or c.get("typeJumpurl"):
                    continue
                tid, name = c.get("typeId"), c.get("typeName")
                if tid is not None and name:
                    classes.append({"type_id": str(tid), "type_name": str(name)})
        videos = []
        home = self._fetch("/anonymous/v1/home/all/list", {"clientType": 3, "pageNum": 1})
        if home is not None:
            videos = self._collect(home)
        return {"class": classes, "filters": {}, "list": videos}

    def homeVideoContent(self):
        home = self._fetch("/anonymous/v1/home/all/list", {"clientType": 3, "pageNum": 1})
        return {"list": self._collect(home) if home is not None else []}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        params = {"pageNum": page, "pageSize": PAGE_SIZE, "type1": str(tid), "sort": 1, "sortBy": 1}
        for k, v in (extend or {}).items():
            if v not in (None, "") and k not in params:
                params[k] = v
        data = self._fetch("/anonymous/video/list", params)
        lst, pages, total = self._paged(data, page)
        if not lst:
            return {"list": [], "page": page, "pagecount": page, "limit": PAGE_SIZE, "total": 0}
        return {
            "list": lst,
            "page": page,
            "pagecount": pages if pages else page,
            "limit": PAGE_SIZE,
            "total": total if total else len(lst),
        }

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        data = self._fetch("/anonymous/video/searchByWordPageable", {"keyword": key, "pageNum": page, "pageSize": 18})
        lst, pages, total = self._paged(data, page)
        if not lst:
            return {"list": [], "page": page, "pagecount": page, "limit": 18, "total": 0}
        return {
            "list": lst,
            "page": page,
            "pagecount": pages if pages else page,
            "limit": 18,
            "total": total if total else len(lst),
        }

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) and ids else ids or "")
        data = self._fetch("/anonymous/video/detail", {"id": vid})
        if not isinstance(data, dict):
            return {"list": []}
        
        name = str(data.get("vodName") or "")
        eps = data.get("episodeList")
        play_url = []
        if isinstance(eps, list):
            for e in eps:
                if not isinstance(e, dict):
                    continue
                nid = e.get("nid")
                if nid is None:
                    continue
                label = str(e.get("name") or "第%s集" % (e.get("sort") or len(play_url) + 1))
                play_url.append("%s$%s|%s" % (label.replace("$", ""), vid, nid))
        if not play_url:
            play_url.append("立即播放$%s|" % vid)

        version = str(data.get("vodVersion") or "")
        from_name = "青花瓷" + version if version else "青花瓷"
        
        extra = []
        for k, v in [("年份", "vodYear"), ("地区", "vodArea"), ("导演", "vodDirector"), ("主演", "vodActor")]:
            if data.get(v):
                extra.append("%s:%s" % (k, data.get(v)))
        if data.get("vodScore"):
            extra.append("评分:%s" % data.get("vodScore"))
            
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": str(data.get("vodPic") or ""),
            "vod_remarks": str(data.get("vodRemarks") or version),
            "vod_content": (data.get("vodContent") or "") + "\n" + " / ".join(extra),
            "vod_play_from": from_name,
            "vod_play_url": "#".join(play_url),
        }
        return {"list": [vod]}

    # ---------------- 专治影视仓重复拼接BUG ----------------
    def playerContent(self, flag, id, vipFlags=None):
        vid, _, nid = str(id or "").partition("|")
        
        play_headers = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Origin": HOST
        }
        
        data = self._fetch("/anonymous/v2/video/episode/url", {"clientType": 3, "id": vid, "nid": nid}, ttl=60)
        items = (data or {}).get("list") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return {"parse": 0, "url": "", "header": json.dumps(play_headers)}
            
        good = [i for i in items if isinstance(i, dict) and str(i.get("url") or "").startswith("http")]
        if not good:
            return {"parse": 0, "url": "", "header": json.dumps(play_headers)}
            
        good.sort(key=lambda i: (
            bool(i.get("needLogin", False)), 
            -(int(i.get("resolution") or 0))
        ))
        
        play_url = str(good[0].get("url") or "")
        if not play_url:
            return {"parse": 0, "url": "", "header": json.dumps(play_headers)}

        # 【终极修复】：移除 playUrl 字段，只保留 url。杜绝影视仓内部因为两个字段同名而导致的拼接 Bug！
        return {
            "parse": 0,
            "url": play_url,
            "header": json.dumps(play_headers)
        }

if __name__ == "__main__":
    s = Spider()
    s.init()
    print(json.dumps(s.homeContent(), ensure_ascii=False)[:400])