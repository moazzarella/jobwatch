#!/usr/bin/env python3
"""Job watch: checks Freelancer.com and Mostaql for new matching jobs and sends them to Telegram.

Standard library only (no pip installs). Runs once per call; schedule it every 15 minutes
with GitHub Actions or macOS launchd.

Environment variables:
  TELEGRAM_BOT_TOKEN   bot token from @BotFather (required)
  TELEGRAM_CHAT_ID     your chat id (required)
  JOBWATCH_SOURCES     comma list of sources to run here: freelancer,mostaql (default: both)
  JOBWATCH_STATE       path of the state file (default: state.json next to this script)
  JOBWATCH_CONFIG      path of the config file (default: config.json next to this script)
  JOBWATCH_RUNNER      label shown in alerts, e.g. "GitHub" or "Mac" (default: "jobwatch")
  JOBWATCH_DRY_RUN     "1" prints messages instead of sending them
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
FAIL_ALERT_AFTER = 3  # consecutive failed runs before a source failure alert


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def http_get(url, accept="text/html", timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": accept,
        "Accept-Language": "ar,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def matches(text, cfg):
    t = text.lower()
    if any(x.lower() in t for x in cfg.get("exclude", [])):
        return False
    return any(k.lower() in t for k in cfg.get("include", []))


# ---------------- sources ----------------

def fetch_freelancer(cfg):
    """Official public API, no login needed."""
    out = {}
    now = time.time()
    max_age = cfg.get("max_age_hours", 24) * 3600
    for q in cfg["queries"]:
        params = urllib.parse.urlencode({
            "query": q, "limit": 30, "compact": "true", "job_details": "true",
            "sort_field": "time_updated", "full_description": "false",
        })
        data = json.loads(http_get(
            "https://www.freelancer.com/api/projects/0.1/projects/active/?" + params,
            accept="application/json"))
        if data.get("status") != "success":
            raise RuntimeError("Freelancer API status: %s" % data.get("status"))
        for p in data["result"]["projects"]:
            if now - p.get("time_submitted", now) > max_age:
                continue
            bids = (p.get("bid_stats") or {}).get("bid_count", 0)
            if bids > cfg.get("max_bids", 150):
                continue
            skills = " ".join(j.get("name", "") for j in (p.get("jobs") or []))
            blob = " ".join([p.get("title", ""), p.get("preview_description", ""), skills])
            if not matches(blob, cfg):
                continue
            b = p.get("budget") or {}
            cur = (p.get("currency") or {}).get("code", "")
            hourly = p.get("type") == "hourly"
            budget = "%s %s–%s%s" % (cur, int(b.get("minimum") or 0),
                                     int(b.get("maximum") or 0), "/hr" if hourly else "")
            out["freelancer:%s" % p["id"]] = {
                "source": "Freelancer",
                "title": p.get("title", "").strip(),
                "url": "https://www.freelancer.com/projects/" + p.get("seo_url", str(p["id"])),
                "budget": budget,
                "bids": "%d bids" % bids,
                "summary": (p.get("preview_description") or "").strip()[:220],
                "skills": skills,
            }
    return out


ROW_RE = re.compile(r'<tr class="project-row">(.*?)</tr>', re.S)
LINK_RE = re.compile(r'<h2[^>]*>\s*<a href="(https://mostaql\.com/project/(\d+)[^"]*)"[^>]*>(.*?)</a>', re.S)
TIME_RE = re.compile(r'<time datetime="([^"]+)"')
BIDS_RE = re.compile(r'hsoub-file-signature-icon"></span>\s*([^<]+?)\s*</li>')
BRIEF_RE = re.compile(r'class="[^"]*project__brief[^"]*"[^>]*>(.*?)</p>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", s))).strip()


def offer_count(text):
    if not text:
        return 0
    if "أضف أول" in text or "لا توجد" in text:
        return 0
    if "عرض واحد" in text:
        return 1
    if "عرضان" in text:
        return 2
    m = re.search(r"\d+", text)
    return int(m.group()) if m else 0


def fetch_mostaql(cfg):
    """Public project listing pages (no login needed)."""
    out = {}
    pages_seen = 0
    for cat in cfg["categories"]:
        for page in range(1, cfg.get("pages", 2) + 1):
            url = "https://mostaql.com/projects?" + urllib.parse.urlencode(
                {"category": cat, "sort": "latest", "page": page})
            body = http_get(url)
            rows = ROW_RE.findall(body)
            if page == 1 and not rows:
                raise RuntimeError("Mostaql returned no project rows (blocked or page changed)")
            pages_seen += 1
            for row in rows:
                m = LINK_RE.search(row)
                if not m:
                    continue
                link, pid, title = m.group(1), m.group(2), clean(m.group(3))
                brief_m = BRIEF_RE.search(row)
                brief = clean(brief_m.group(1)) if brief_m else ""
                bids_m = BIDS_RE.search(row)
                bids_txt = clean(bids_m.group(1)) if bids_m else ""
                n = offer_count(bids_txt)
                if n > cfg.get("max_bids", 40):
                    continue
                t_m = TIME_RE.search(row)
                if not matches(title + " " + brief, cfg):
                    continue
                out["mostaql:%s" % pid] = {
                    "source": "Mostaql",
                    "title": title,
                    "url": link.split("?")[0],
                    "budget": "",
                    "bids": bids_txt or "0 عروض",
                    "summary": brief[:220],
                    "posted": t_m.group(1) if t_m else "",
                }
    if not pages_seen:
        raise RuntimeError("Mostaql: no pages fetched")
    return out


SOURCES = {"freelancer": fetch_freelancer, "mostaql": fetch_mostaql}


# ---------------- telegram ----------------

def tg_send(text, dry):
    if dry:
        print("---- TELEGRAM ----\n" + text + "\n------------------")
        return
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    for attempt in range(3):
        try:
            urllib.request.urlopen(
                "https://api.telegram.org/bot%s/sendMessage" % token, data=data, timeout=30).read()
            time.sleep(1.1)  # stay under Telegram's per-chat rate limit
            return
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(5)
                continue
            raise


def format_job(j):
    e = html.escape
    lines = ["<b>%s</b> · %s" % (e(j["source"]), e(j["bids"]))]
    lines.append('<a href="%s">%s</a>' % (e(j["url"], quote=True), e(j["title"])))
    if j.get("budget"):
        lines.append("💰 " + e(j["budget"]))
    if j.get("summary"):
        lines.append(e(j["summary"]))
    return "\n".join(lines)


# ---------------- main ----------------

def main():
    config = load_json(os.environ.get("JOBWATCH_CONFIG", os.path.join(HERE, "config.json")), None)
    if not config:
        sys.exit("config.json missing or invalid")
    state_path = os.environ.get("JOBWATCH_STATE", os.path.join(HERE, "state.json"))
    state = load_json(state_path, {"seen": {}, "fails": {}, "initialized": []})
    runner = os.environ.get("JOBWATCH_RUNNER", "jobwatch")
    dry = os.environ.get("JOBWATCH_DRY_RUN") == "1"
    wanted = [s.strip() for s in os.environ.get(
        "JOBWATCH_SOURCES", "freelancer,mostaql").split(",") if s.strip()]

    now = int(time.time())
    for src in wanted:
        if src not in SOURCES or not config.get(src, {}).get("enabled", True):
            continue
        try:
            jobs = SOURCES[src](config[src])
        except Exception as ex:  # network block, captcha page, changed HTML, ...
            n = state["fails"].get(src, 0) + 1
            state["fails"][src] = n
            log("%s failed (%d in a row): %s" % (src, n, ex))
            if n == FAIL_ALERT_AFTER:
                tg_send("⚠️ <b>%s</b> on %s failed %d times in a row:\n%s" % (
                    html.escape(src), html.escape(runner), n, html.escape(str(ex))[:300]), dry)
            continue
        if state["fails"].get(src, 0) >= FAIL_ALERT_AFTER:
            tg_send("✅ <b>%s</b> on %s is working again." % (html.escape(src), html.escape(runner)), dry)
        state["fails"][src] = 0

        new = [(k, v) for k, v in jobs.items() if k not in state["seen"]]
        first_run = src not in state["initialized"]
        for k, _ in new:
            state["seen"][k] = now
        if first_run:
            state["initialized"].append(src)
            tg_send("👀 Now watching <b>%s</b> from %s. %d matching jobs are already open; "
                    "you'll get new ones as they're posted." % (
                        html.escape(src), html.escape(runner), len(new)), dry)
            log("%s initialized with %d jobs" % (src, len(new)))
            continue
        log("%s: %d matches, %d new" % (src, len(jobs), len(new)))
        for _, job in new[:10]:
            tg_send(format_job(job), dry)

    # forget jobs older than 14 days so the state file stays small
    cutoff = now - 14 * 86400
    state["seen"] = {k: t for k, t in state["seen"].items() if t >= cutoff}
    save_json(state_path, state)


if __name__ == "__main__":
    main()
