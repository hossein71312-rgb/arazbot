import html, json, os, re, sys, time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import requests

TOKEN = os.environ.get("RUBIKA_TOKEN", "")
CHAT = os.environ.get("RUBIKA_CHAT_ID", "")
BASE = "https://botapi.rubika.ir/v3/%s/" % TOKEN
UA = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}


def api(method, data=None):
    r = requests.post(BASE + method, json=data or {}, timeout=60)
    try:
        j = r.json()
    except Exception:
        raise SystemExit("پاسخ نامعتبر از روبیکا (%s): %s" % (r.status_code, r.text[:300]))
    if j.get("status") != "OK":
        raise SystemExit("خطای روبیکا در %s: %s" % (method, json.dumps(j, ensure_ascii=False)[:400]))
    return j.get("data", {})


def clean(t, n):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def parse_feed(data, name):
    root = ET.fromstring(data)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).timestamp()
        except Exception:
            ts = time.time()
        out.append({"title": title, "link": link, "desc": it.findtext("description") or "", "ts": ts, "src": name})
    return out


def fetch_all(cfg, verbose=False):
    items = []
    for f in cfg["feeds"]:
        try:
            r = requests.get(f["url"], headers=UA, timeout=30)
            r.raise_for_status()
            got = parse_feed(r.content, f["name"])
            items += got
            if verbose:
                print("✅ %s: %d خبر" % (f["name"], len(got)))
        except Exception as e:
            print("❌ %s: %s" % (f["name"], str(e)[:200]))
    return items


def make_text(i, cfg):
    desc = clean(i["desc"], cfg.get("desc_chars", 220))
    lines = ["📰 " + i["title"], ""]
    if desc:
        lines += [desc, ""]
    lines += ["🔗 " + i["link"], "منبع: " + i["src"], "", cfg.get("hashtag", "#اخبار_تکنولوژی")]
    return "\n".join(lines)


def cmd_test(cfg):
    print("ربات:", json.dumps(api("getMe"), ensure_ascii=False)[:200])
    fetch_all(cfg, verbose=True)
    if CHAT:
        api("sendMessage", {"chat_id": CHAT, "text": "✅ تست ربات اخبار"})
        print("پیام تست فرستاده شد")
    else:
        print("RUBIKA_CHAT_ID خالی است")


def cmd_post(cfg):
    items = fetch_all(cfg)
    if not items:
        raise SystemExit("هیچ خبری از منابع گرفته نشد")
    st = {"seen": []}
    if os.path.exists("state.json"):
        st = json.load(open("state.json", encoding="utf-8"))
    seen = list(st["seen"])
    items.sort(key=lambda x: x["ts"])
    if not seen:
        seen = [i["link"] for i in items[:-3]]
    sset = set(seen)
    now = time.time()
    maxage = cfg.get("max_age_hours", 24) * 3600
    fresh = []
    for i in items:
        if i["link"] in sset:
            continue
        if now - i["ts"] > maxage:
            seen.append(i["link"])
        else:
            fresh.append(i)
    for i in fresh[: cfg.get("max_per_run", 1)]:
        api("sendMessage", {"chat_id": CHAT, "text": make_text(i, cfg)})
        seen.append(i["link"])
        print("ارسال شد:", i["title"])
        time.sleep(2)
    if not fresh:
        print("خبر تازه‌ای نبود")
    json.dump({"seen": seen[-1000:]}, open("state.json", "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("RUBIKA_TOKEN تنظیم نشده")
    cfg = json.load(open("config.json", encoding="utf-8"))
    if (sys.argv[1] if len(sys.argv) > 1 else "post") == "test":
        cmd_test(cfg)
    else:
        if not CHAT:
            raise SystemExit("RUBIKA_CHAT_ID تنظیم نشده")
        cmd_post(cfg)
