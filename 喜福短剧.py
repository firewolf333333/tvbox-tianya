# -*- coding: utf-8 -*-
"""
喜福短剧 - minidrama.contentchina.com
Nuxt.js(Vue SSR) 站点，业务数据全走 JSON API；播放为阿里云 VOD，需用 STS 凭证
签名调用 GetPlayInfo 接口取直链。

关键结论（已实测验证）：
1. 站点品牌「喜福网」，Nuxt SSR 外壳，实际数据接口域名 https://minidrama-api.contentchina.com
2. 接口（均为 GET，需 Referer/Origin 为站点域名）：
   - 分类：/web/v1/home/categoryList → {categories:[{id,name,sort}]}
   - 列表：/web/v1/drama/list?currentPage={pg}&pageSize={n}&filterCategories={cid}
           → {data:[item], pagination:{total, pageNum, pageSize}}
   - 详情：/web/v1/drama/detail?albumId={id}
           → {episodeList:[{sequence,vid,episodeId}], serialData:{title,coverUrl,
              introduction,leadActor,categories,total,score,recordNumber}, guessList}
   - 播放授权：/web/v1/drama/play_auth?albumId={id}&seq={n}
           → {playAuth(base64), domain, vid}。playAuth 解码后含
             AccessKeyId / AccessKeySecret / SecurityToken / VideoMeta.VideoId / Region。
3. 播放链路（核心）：阿里云 VOD
   - 用 playAuth 里的 STS 三元组，对 https://vod.{region}.aliyuncs.com/ 调用
     RPC 接口 GetPlayInfo（HMAC-SHA1 签名，Key = AccessKeySecret + "&"），
     参数需带 ResultType=Multiple（否则加密流会报 Forbidden.AliyunVoDEncryption）。
   - 返回 PlayInfoList.PlayInfo[]，其中 **Encrypt=0 的 mp4 为未加密直链，可直连播放**
     （实测 206 video/mp4）；m3u8 为阿里云私有加密（EncryptType=AliyunVoDEncryption），
     需阿里播放器解密，TVBox 不可直接播，故插件优先选未加密 mp4。
4. 搜索：站点**没有搜索接口**（前端亦无搜索入口）。插件通过在
   /web/v1/drama/list 拉全量（total 约 225）后按片名本地过滤实现。
"""
import re
import json
import time
import uuid
import hmac
import base64
import hashlib
import requests
from datetime import datetime, timezone
from urllib.parse import quote

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def __init__(self):
            pass


class Spider(Spider):
    # ==================== 基础配置 ====================
    name = "喜福短剧"
    site_url = "https://minidrama.contentchina.com"
    api_url = "https://minidrama-api.contentchina.com"

    searchable = 1
    quickSearch = 1
    filterable = 0
    changeable = 1

    # 分类（来自 /web/v1/home/categoryList）：id / 名称
    class_name = ["全部", "现代言情", "爽剧", "都市", "逆袭", "甜宠", "女强", "虐恋", "古代言情", "玄幻"]
    class_url = ["0", "1", "3", "4", "5", "6", "7", "13", "16", "23"]

    PAGE_SIZE = 24

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://minidrama.contentchina.com/",
        "Origin": "https://minidrama.contentchina.com",
        "Connection": "keep-alive",
    }

    play_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://minidrama.contentchina.com/",
        "Accept": "*/*",
    }

    def __init__(self):
        super().__init__()
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        self._play_cache = {}
        self._cache_ttl = 1500
        self._last_req_time = 0
        self._min_req_interval = 0.6

    # ==================== 工具方法 ====================
    def _log(self, msg):
        print("[%s] %s" % (self.name, msg))

    def _clean_html(self, text):
        if not text:
            return ""
        text = re.sub(r'<br\s*/?>', ' ', str(text))
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
        return re.sub(r'\s+', ' ', text).strip()

    def _fix_pic(self, pic):
        if not pic:
            return ""
        pic = str(pic).strip()
        if pic.startswith("//"):
            return "https:" + pic
        return pic

    # ==================== 请求基础 ====================
    def _apply_req_delay(self):
        now = time.time()
        elapsed = now - self._last_req_time
        if 0 < elapsed < self._min_req_interval:
            time.sleep(self._min_req_interval - elapsed)
        self._last_req_time = time.time()

    def fetch(self, url, headers=None, timeout=25):
        self._apply_req_delay()
        return self._session.get(url, headers=headers or self.headers, timeout=timeout)

    def _get_json(self, path, max_retry=3):
        url = path if path.startswith("http") else (self.api_url + path)
        try:
            for attempt in range(max_retry):
                resp = self.fetch(url)
                if resp.status_code != 200:
                    if attempt < max_retry - 1:
                        time.sleep(1 + attempt)
                        continue
                    return {}
                try:
                    return resp.json()
                except Exception:
                    if attempt < max_retry - 1:
                        time.sleep(1 + attempt)
                        continue
                    return {}
            return {}
        except Exception as e:
            self._log("请求失败: %s, %s" % (url, e))
            return {}

    # ==================== 阿里云 VOD 签名 ====================
    @staticmethod
    def _pe(s):
        return quote(str(s), safe="~")

    def _vod_get_play_info(self, auth):
        """用 playAuth 解出的 STS 凭证调用阿里云 VOD GetPlayInfo，返回直链列表"""
        try:
            j = json.loads(base64.b64decode(auth["playAuth"] + "=" * ((4 - len(auth["playAuth"]) % 4) % 4)))
        except Exception as e:
            self._log("playAuth 解码失败: %s" % e)
            return []
        ak = j.get("AccessKeyId", "")
        sk = j.get("AccessKeySecret", "")
        token = j.get("SecurityToken", "")
        vid = (j.get("VideoMeta") or {}).get("VideoId", "") or auth.get("vid", "")
        region = j.get("Region", "cn-shenzhen")
        if not (ak and sk and vid):
            self._log("playAuth 缺少凭证字段")
            return []
        params = {
            "Action": "GetPlayInfo",
            "VideoId": vid,
            "ResultType": "Multiple",
            "Formats": "mp4,m3u8",
            "AccessKeyId": ak,
            "SecurityToken": token,
            "Format": "JSON",
            "Version": "2017-03-21",
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": str(uuid.uuid4()),
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        canonical = "&".join("%s=%s" % (self._pe(k), self._pe(params[k])) for k in sorted(params))
        string_to_sign = "GET&%s&%s" % (self._pe("/"), self._pe(canonical))
        sig = base64.b64encode(hmac.new((sk + "&").encode("utf-8"),
                                        string_to_sign.encode("utf-8"),
                                        hashlib.sha1).digest()).decode()
        url = "https://vod.%s.aliyuncs.com/?Signature=%s&%s" % (region, self._pe(sig), canonical)
        try:
            resp = self.fetch(url, headers={"User-Agent": self.headers["User-Agent"]}, timeout=25)
            data = resp.json()
        except Exception as e:
            self._log("GetPlayInfo 调用失败: %s" % e)
            return []
        infos = (data.get("PlayInfoList") or {}).get("PlayInfo") or []
        return infos

    # ==================== 列表/详情解析 ====================
    def _parse_items(self, data):
        videos = []
        for it in (data or []):
            vid = it.get("albumId")
            if vid is None:
                continue
            total = it.get("total")
            remark = "共%s集" % total if total else ""
            videos.append({
                "vod_id": str(vid),
                "vod_name": it.get("title", "") or "",
                "vod_pic": self._fix_pic(it.get("coverUrl", "")),
                "vod_remarks": remark,
            })
        return videos

    # ==================== 播放地址解析 ====================
    def _resolve_play_url(self, album_id, seq):
        cache_key = "%s-%s" % (album_id, seq)
        now = time.time()
        if cache_key in self._play_cache:
            url, ts = self._play_cache[cache_key]
            if now - ts < self._cache_ttl:
                return url
        auth = self._get_json("/web/v1/drama/play_auth?albumId=%s&seq=%s" % (album_id, seq))
        if str(auth.get("code")) != "200" or not auth.get("data"):
            self._log("play_auth 失败: %s" % str(auth)[:120])
            return ""
        infos = self._vod_get_play_info(auth["data"])
        if not infos:
            self._log("GetPlayInfo 无结果")
            return ""
        plain_mp4 = None
        plain_m3u8 = None
        any_url = ""
        for p in infos:
            u = p.get("PlayURL", "")
            if not u:
                continue
            if not any_url:
                any_url = u
            if str(p.get("Encrypt", "0")) == "0":
                if p.get("Format") == "mp4" and not plain_mp4:
                    plain_mp4 = u
                elif p.get("Format") == "m3u8" and not plain_m3u8:
                    plain_m3u8 = u
        url = plain_mp4 or plain_m3u8 or any_url
        if url:
            self._log("播放直链: %s" % url[:90])
            self._play_cache[cache_key] = (url, now)
        return url

    # ==================== TVBox 核心方法 ====================
    def init(self, extend=''):
        self._log("初始化完成")

    def homeContent(self, filter=False):
        return {
            "class": [{"type_id": tid, "type_name": name}
                      for tid, name in zip(self.class_url, self.class_name)]
        }

    def homeVideoContent(self):
        try:
            data = self._get_json("/web/v1/drama/list?currentPage=1&pageSize=30")
            items = (data.get("data") or {}).get("data") or []
            return {"list": self._parse_items(items)[:30]}
        except Exception as e:
            self._log("homeVideoContent异常: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            path = "/web/v1/drama/list?currentPage=%d&pageSize=%d" % (pg, self.PAGE_SIZE)
            if str(tid) not in ("", "0", "None"):
                path += "&filterCategories=%s" % tid
            self._log("分类请求: %s" % path)
            data = self._get_json(path)
            body = data.get("data") or {}
            items = body.get("data") or []
            pg_info = body.get("pagination") or {}
            total = pg_info.get("total") or len(items)
            pagecount = int((total + self.PAGE_SIZE - 1) // self.PAGE_SIZE) if total else 1
            return {
                "list": self._parse_items(items),
                "page": pg,
                "pagecount": max(1, pagecount),
                "limit": self.PAGE_SIZE,
                "total": total,
            }
        except Exception as e:
            self._log("categoryContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": self.PAGE_SIZE, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            keyword = str(key or "").strip().lower()
            if not keyword:
                return {"page": 1, "pagecount": 1, "limit": 30, "total": 0, "list": []}
            self._log("搜索(本地过滤): %s" % keyword)
            data = self._get_json("/web/v1/drama/list?currentPage=1&pageSize=1000")
            items = (data.get("data") or {}).get("data") or []
            hits = [it for it in items if keyword in str(it.get("title", "")).lower()]
            videos = self._parse_items(hits)
            return {"list": videos, "page": 1, "pagecount": 1, "limit": 30, "total": len(videos)}
        except Exception as e:
            self._log("searchContent异常: %s" % e)
            return {"list": [], "page": 1, "pagecount": 1, "limit": 30, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            self._log("详情请求: albumId=%s" % vod_id)
            data = self._get_json("/web/v1/drama/detail?albumId=%s" % vod_id)
            body = data.get("data") or {}
            sd = body.get("serialData") or {}
            eps = body.get("episodeList") or []
            if not sd and not eps:
                return {"list": []}
            actors = sd.get("leadActor") or []
            if isinstance(actors, list):
                actors = ",".join(str(a) for a in actors)
            cats = sd.get("categories") or []
            if isinstance(cats, list):
                cats = ",".join(str(a) for a in cats)
            ep_list = []
            for ep in sorted(eps, key=lambda x: int(x.get("sequence", 0) or 0)):
                seq = ep.get("sequence")
                if seq is None:
                    continue
                ep_list.append({"name": "第%s集" % seq, "link": "%s-%s" % (vod_id, seq)})
            if not ep_list:
                self._log("无剧集")
                return {"list": []}
            video = {
                "vod_id": vod_id,
                "vod_name": sd.get("title", "") or "未知",
                "vod_pic": self._fix_pic(sd.get("coverUrl", "")),
                "vod_content": self._clean_html(sd.get("introduction", "")),
                "vod_actor": actors,
                "vod_remarks": cats,
                "vod_play_from": "喜福",
                "vod_play_url": "#".join("%s$%s" % (e["name"], e["link"]) for e in ep_list),
            }
            self._log("详情解析成功: %s 集数:%d" % (video["vod_name"], len(ep_list)))
            return {"list": [video]}
        except Exception as e:
            self._log("detailContent异常: %s" % e)
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            parts = str(id).split("-")
            if len(parts) < 2:
                return {"parse": 0, "url": "", "header": ""}
            album_id, seq = parts[0], parts[1]
            url = self._resolve_play_url(album_id, seq)
            if not url:
                return {"parse": 0, "url": "", "header": ""}
            return {"parse": 0, "url": url, "header": self.play_headers.copy()}
        except Exception as e:
            self._log("playerContent异常: %s" % e)
            return {"parse": 0, "url": "", "header": ""}

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass
