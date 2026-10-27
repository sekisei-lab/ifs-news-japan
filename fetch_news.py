import json, time, concurrent.futures, urllib.request, urllib.parse, re, html
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

TOPICS = {
    "IFS 全般": ['"IFS Cloud"', '"IFSジャパン"', '"IFS Japan"'],
    "導入・事例": ['IFS Cloud 導入', 'IFS Cloud 導入事例', 'IFS ERP 採用', 'IFS JAL', 'IFS 日本航空', 'IFS 航空 導入'],
    "提携・パートナー": ['IFS パートナー 提携', 'IFS Cloud 協業'],
    "製品・AI": ['IFS Cloud AI', 'IFS Industrial AI', 'IFS Nexus Black'],
    "イベント・セミナー": ['IFS セミナー ウェビナー', 'IFS Connect Japan'],
}
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def parse(xml_bytes, source_hint):
    out = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = html.unescape(it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        try:
            ts = parsedate_to_datetime(pub).timestamp()
        except Exception:
            ts = 0
        src = it.findtext("source") or it.findtext("{https://www.bing.com/news/search}Source") or source_hint
        if " - " in title and source_hint == "Google News":
            title, _, s2 = title.rpartition(" - ")
            src = s2 or src
        out.append({"title": title, "link": link, "ts": ts, "source": src})
    return out


def key(e):
    return re.sub(r"\W", "", e["title"])[:40]


def real_url(link):
    if "bing.com" in link:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
        return (q.get("url") or [""])[0]
    if "news.google.com" in link:
        gid = link.split("/articles/")[1].split("?")[0]
        page = fetch(f"https://news.google.com/articles/{gid}").decode("utf-8", "replace")
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        req = json.dumps([[["Fbv4je", json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], gid, int(ts.group(1)), sg.group(1)]), None, "generic"]]])
        r = urllib.request.Request("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                                   data=("f.req=" + urllib.parse.quote(req)).encode(),
                                   headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        body = urllib.request.urlopen(r, timeout=15).read().decode("utf-8", "replace")
        return re.search(r'garturlres\\",\\"(.*?)\\"', body).group(1)
    return link


def summarize(e):
    try:
        raw = urllib.request.urlopen(urllib.request.Request(real_url(e["link"]), headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read(300000)
        page = raw.decode("utf-8", "replace")
        for pat in (r'<meta[^>]+(?:property|name)=["\x27]og:description["\x27][^>]+content=["\x27]([^"\x27]*)',
                    r'<meta[^>]+content=["\x27]([^"\x27]*)["\x27][^>]+(?:property|name)=["\x27]og:description',
                    r'<meta[^>]+name=["\x27]description["\x27][^>]+content=["\x27]([^"\x27]*)'):
            m = re.search(pat, page, re.I)
            if m and len(m.group(1)) > 20:
                return html.unescape(m.group(1)).strip()[:160]
    except Exception as ex:
        print("summary fail", e["title"][:30], ex)
    return ""


def collect():
    items, seen = [], set()
    for topic, queries in TOPICS.items():
        for q in queries:
            enc = urllib.parse.quote(q)
            urls = [
                (f"https://news.google.com/rss/search?q={enc}+when:1y&hl=ja&gl=JP&ceid=JP:ja", "Google News"),
                (f"https://www.bing.com/news/search?q={enc}&format=rss&mkt=ja-JP", "Bing News"),
            ]
            for url, hint in urls:
                try:
                    for e in parse(fetch(url), hint):
                        key = re.sub(r"\W", "", e["title"])[:40]
                        if key in seen:
                            continue
                        t = e["title"].lower()
                        if "ifs" not in t and "ｉｆｓ" not in t:
                            continue
                        seen.add(key)
                        e["topic"] = topic
                        items.append(e)
                except Exception as ex:
                    print("fetch fail", q, hint, ex)
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items



if __name__ == "__main__":
    path = Path(__file__).parent / "news.json"
    items = collect()
    if items:
        old = json.loads(path.read_text(encoding="utf-8"))["items"] if path.exists() else []
        have = {re.sub(r"\W", "", e["title"])[:40] for e in items}
        items += [e for e in old if re.sub(r"\W", "", e["title"])[:40] not in have]
        items.sort(key=lambda x: x["ts"], reverse=True)
        items = items[:1000]
        prev = {key(e): e for e in old}
        for e in items:
            if key(e) in prev and "summary" in prev[key(e)]:
                e["summary"] = prev[key(e)]["summary"]
        todo = [e for e in items if "summary" not in e][:80]
        with concurrent.futures.ThreadPoolExecutor(8) as ex:
            for e, sm in zip(todo, ex.map(summarize, todo)):
                e["summary"] = sm
        Path(__file__).parent.joinpath("news.json").write_text(
            json.dumps({"updated": time.time(), "items": items}, ensure_ascii=False), encoding="utf-8")
    print(len(items), "items")
