# coding=utf-8
"""
目标站: 365短剧 (www.365jcw.com)
易优CMS(EyouCMS) 产品模型，短剧按 /product/ 详情、/news/ 播放页组织
"""
import re
import sys
import json
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "http://www.365jcw.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        # 分类来自站点导航(info/N.html)，短剧类在前，影视类在后
        self.categories = [
            {"type_id": "27", "type_name": "抖音短剧"},
            {"type_id": "39", "type_name": "都市爽剧"},
            {"type_id": "40", "type_name": "浪漫言情"},
            {"type_id": "41", "type_name": "修仙玄幻"},
            {"type_id": "42", "type_name": "脑洞悬疑"},
            {"type_id": "43", "type_name": "年代穿越"},
            {"type_id": "44", "type_name": "有声动漫"},
            {"type_id": "45", "type_name": "现代都市"},
            {"type_id": "46", "type_name": "365影视"},
            {"type_id": "47", "type_name": "女频恋爱"},
            {"type_id": "48", "type_name": "反转爽剧"},
            {"type_id": "49", "type_name": "古装仙侠"},
            {"type_id": "1",  "type_name": "电影"},
            {"type_id": "2",  "type_name": "电视剧"},
            {"type_id": "3",  "type_name": "综艺"},
            {"type_id": "4",  "type_name": "动漫"},
        ]

    def _parse_video_list(self, soup, max_count=0):
        """通用视频列表解析器，兼容首页/分类/搜索页的 hl-list-item 卡片"""
        video_list = []
        seen = set()

        # 主选择器：产品卡片缩略图
        cards = soup.select('a.hl-item-thumb')
        if not cards:
            cards = soup.select('li.hl-list-item a')

        for a in cards:
            href = a.get('href', '')
            m = re.search(r'/product/(\d+)\.html', href)
            if not m:
                continue
            vod_id = m.group(1)
            if vod_id in seen:
                continue
            seen.add(vod_id)
            title = a.get('title', '') or a.get_text(strip=True)
            if not title:
                continue
            pic = a.get('data-original', '') or a.get('src', '')
            remark = ''
            remark_elem = a.select_one('.hl-pic-text') or a.select_one('.hl-remarks')
            if remark_elem:
                remark = remark_elem.get_text(strip=True)
            video_list.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark
            })
            if max_count > 0 and len(video_list) >= max_count:
                break

        # 兜底：任意 /product/ 链接
        if not video_list:
            for a in soup.select('a[href*="/product/"]'):
                href = a.get('href', '')
                m = re.search(r'/product/(\d+)\.html', href)
                if not m:
                    continue
                vod_id = m.group(1)
                if vod_id in seen:
                    continue
                seen.add(vod_id)
                title = a.get('title', '') or a.get_text(strip=True)
                if not title:
                    continue
                pic = a.get('data-original', '') or a.get('src', '')
                video_list.append({
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": ""
                })
                if max_count > 0 and len(video_list) >= max_count:
                    break
        return video_list

    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            video_list = self._parse_video_list(soup, max_count=36)
        return {"class": self.categories, "list": video_list, "filters": {}}

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if page <= 1:
            url = f"{self.site_url}/info/{tid}.html"
        else:
            url = f"{self.site_url}/info/{tid}-{page}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}

        soup = BeautifulSoup(resp.text, 'html.parser')
        video_list = self._parse_video_list(soup)

        pagecount = page
        # 分页文本形如 "1 / 1314页"
        total_text = soup.get_text()
        pt = re.search(r'(\d+)\s*/\s*(\d+)\s*页', total_text)
        if pt:
            pagecount = int(pt.group(2))
        # 兜底：从分页链接里取最大页码
        for a in soup.select('a[href*="/info/"]'):
            mm = re.search(r'/info/%s-(\d+)\.html' % tid, a.get('href', ''))
            if mm:
                pagecount = max(pagecount, int(mm.group(1)))

        total = 0
        tt = re.search(r'共\s*(\d+)\s*个', total_text)
        if tt:
            total = int(tt.group(1))
        if not total:
            total = len(video_list) * pagecount
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": total
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        url = f"{self.site_url}/product/{vod_id}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}

        soup = BeautifulSoup(resp.text, 'html.parser')

        # 标题：从 <title> 的 《》 内提取
        vod_name = vod_id
        title_tag = soup.select_one('title')
        if title_tag:
            raw = title_tag.get_text()
            m = re.search(r'《([^》]+)》', raw)
            vod_name = m.group(1).strip() if m else raw.strip()
        if vod_name == vod_id:
            h1 = soup.select_one('h1')
            if h1:
                vod_name = h1.get_text(strip=True)

        # 封面：首个 data-original
        vod_pic = ''
        img = soup.select_one('img[data-original]')
        if img:
            vod_pic = img.get('data-original', '')
        if not vod_pic:
            img = soup.select_one('.hl-item-thumb') or soup.select_one('img')
            if img:
                vod_pic = img.get('data-original', '') or img.get('src', '')

        # 简介
        vod_content = ''
        em = soup.select_one('.hl-content-text em') or soup.select_one('.hl-content-text')
        if em:
            vod_content = em.get_text(' ', strip=True)
            vod_content = re.sub(r'^该[^，]*讲述的是', '', vod_content)
            vod_content = re.sub(r'，[^，]+是由.*?上映[。]?$', '', vod_content)
            vod_content = vod_content.strip('，。 ')
            if vod_content in ('暂无简介',):
                vod_content = ''

        # 主演/导演/年份/地区
        vod_actor = vod_director = vod_area = vod_year = ''
        for li in soup.select('li'):
            text = li.get_text(strip=True)
            if '主演' in text:
                vod_actor = text.split('：', 1)[-1].strip()
            elif '导演' in text:
                vod_director = text.split('：', 1)[-1].strip()
            elif '年份' in text:
                vod_year = text.split('：', 1)[-1].strip()
            elif '地区' in text:
                vod_area = text.split('：', 1)[-1].strip()

        # 选集：播放列表 #playlist 内 /news/{id}-{线路}-{集}.html
        play_from_list = []
        play_url_list = []
        playlist = soup.select_one('#playlist') or soup
        groups = {}
        for a in playlist.select('a[href*="/news/"]'):
            href = a.get('href', '')
            m = re.search(r'/news/(\d+)-(\d+)-(\d+)\.html', href)
            if not m:
                continue
            line = m.group(2)
            ep_name = a.get('title', '') or a.get_text(strip=True)
            if not ep_name:
                continue
            if not href.startswith('http'):
                href = self.site_url + href
            groups.setdefault(line, []).append(f"{ep_name}${href}")

        for line in sorted(groups.keys(), key=lambda x: int(x)):
            play_from_list.append(f"线路{int(line) + 1}")
            play_url_list.append('#'.join(groups[line]))

        if not play_url_list:
            play_from_list.append('默认线路')
            play_url_list.append(f"播放${self.site_url}/news/{vod_id}-0-0.html")

        vod_play_from = '$$$'.join(play_from_list)
        vod_play_url = '$$$'.join(play_url_list)

        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_area": vod_area,
            "vod_year": vod_year,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        url = f"{self.site_url}/search.php?searchword={encoded_key}"
        if page > 1:
            url += f"&page={page}"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1}
        soup = BeautifulSoup(resp.text, 'html.parser')
        video_list = self._parse_video_list(soup)
        return {"list": video_list, "page": page, "pagecount": 1}

    def playerContent(self, flag, id, vipFlags):
        if id.startswith('http'):
            play_url = id
        elif id.startswith('/'):
            play_url = self.site_url + id
        elif re.match(r'\d+-\d+-\d+', id):
            play_url = f"{self.site_url}/news/{id}.html"
        else:
            play_url = f"{self.site_url}/news/{id}.html"

        resp = self.fetch(play_url, headers=self.headers)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.headers}

        html = resp.text

        # 当前集真实地址： var now="https://...m3u8"
        now_match = re.search(r'var\s+now\s*=\s*"([^"]+)"', html)
        if now_match:
            video_url = now_match.group(1)
            if video_url and video_url.startswith('http'):
                return {"parse": 0, "url": video_url, "header": self.headers}

        # 兜底：直接抽取 m3u8
        m3u8 = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
        if m3u8:
            return {"parse": 0, "url": m3u8.group(0), "header": self.headers}

        # 再兜底：iframe 内继续找
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            iframe_url = iframe.group(1)
            if not iframe_url.startswith('http'):
                iframe_url = self.site_url + iframe_url if iframe_url.startswith('/') else self.site_url + '/' + iframe_url
            iframe_resp = self.fetch(iframe_url, headers=self.headers)
            if iframe_resp:
                iframe_html = iframe_resp.text
                m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', iframe_html)
                if m:
                    return {"parse": 0, "url": m.group(0), "header": self.headers}

        return {"parse": 1, "url": play_url, "header": self.headers}
