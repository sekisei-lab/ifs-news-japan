import json, time, urllib.request, urllib.parse, re, html
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

TOPICS = {
    "IFS 全般": ['"IFS Cloud"', '"IFSジャパン"', '"IFS Japan"'],
    "導入・事例": ['IFS Cloud 導入', 'IFS Cloud 導入事例', 'IFS ERP 採用'],
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


def collect():
    items, seen = [], set()
    for topic, queries in TOPICS.items():
        for q in queries:
            enc = urllib.parse.quote(q)
            urls = [
                (f"https://news.google.com/rss/search?q={enc}+when:30d&hl=ja&gl=JP&ceid=JP:ja", "Google News"),
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
    return items[:200]



if __name__ == "__main__":
    items = collect()
    if items:
        Path(__file__).parent.joinpath("news.json").write_text(
            json.dumps({"updated": time.time(), "items": items}, ensure_ascii=False), encoding="utf-8")
    print(len(items), "items")
