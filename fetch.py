"""Fetch fresh postings for one person, filter them, and write people/<name>/new_jobs.json."""
import html
import json
import re
import sys
import time

import requests
from jobspy import scrape_jobs

import person

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}


def strip_html(s):
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def jobspy_jobs(cfg):
    jobs = []
    searches = [dict(search_term=t, location=cfg["search_location"], country_indeed=cfg["country"],
                     site_name=["indeed"]) for t in cfg["search_terms"]]
    for t in cfg["linkedin_terms"]:
        searches += [dict(search_term=t, location=cfg["search_location"], site_name=["linkedin"]),
                     dict(search_term=t, location=cfg["country"].title(), is_remote=True, site_name=["linkedin"])]
    for s in searches:
        try:
            df = scrape_jobs(results_wanted=cfg["results_per_search"], hours_old=cfg["hours_old"], verbose=0, **s)
        except Exception as e:
            print(f"jobspy failed for {s['search_term']!r} {s['location']}: {e}")
            continue
        for r in df.fillna("").to_dict("records"):
            jobs.append({
                "url": r["job_url"], "title": r["title"], "company": r["company"],
                "location": r["location"], "remote": bool(r["is_remote"]) or s.get("is_remote", False),
                "posted": str(r["date_posted"]), "source": r["site"], "description": r["description"],
            })
        time.sleep(15 if s["site_name"] == ["linkedin"] else 3)
    return jobs


def getonbrd_jobs(cfg):
    jobs, companies = [], {}
    cutoff = time.time() - cfg["hours_old"] * 3600
    for cat in cfg.get("getonbrd_categories") or []:
        data = requests.get(f"https://www.getonbrd.com/api/v0/categories/{cat}/jobs",
                            params={"per_page": 100}, timeout=30).json()["data"]
        for j in data:
            a = j["attributes"]
            remote = a["remote_modality"] == "fully_remote"
            junior = a["seniority"]["data"]["id"] in (1, 2)  # no experience / junior
            if a["published_at"] < cutoff or not junior or not (remote or cfg["country"].title() in a["countries"]):
                continue
            cid = a["company"]["data"]["id"]
            if cid not in companies:
                companies[cid] = requests.get(f"https://www.getonbrd.com/api/v0/companies/{cid}",
                                              timeout=30).json()["data"]["attributes"]["name"]
            jobs.append({
                "url": j["links"]["public_url"], "title": a["title"], "company": companies[cid],
                "location": ", ".join(a["countries"]) or "Remote", "remote": remote,
                "posted": time.strftime("%Y-%m-%d", time.localtime(a["published_at"])), "source": "getonbrd",
                "description": strip_html("\n".join(a[k] or "" for k in ("description", "functions", "desirable"))),
                "junior": True,
            })
    return jobs


def board_jobs(cfg):
    jobs, b = [], cfg.get("boards") or {}

    def add(url, title, company, location, remote, posted, source, description):
        remote = remote or "remote" in location.lower()
        jobs.append(dict(url=url, title=title, company=company, location=location, remote=remote,
                         posted=posted, source=source, description=description))

    for co in b.get("greenhouse") or []:
        for j in requests.get(f"https://boards-api.greenhouse.io/v1/boards/{co}/jobs?content=true", timeout=30).json()["jobs"]:
            add(j["absolute_url"], j["title"], j.get("company_name") or co, j["location"]["name"], False,
                j["updated_at"][:10], "greenhouse", strip_html(html.unescape(j["content"])))
    for co in b.get("lever") or []:
        for j in requests.get(f"https://api.lever.co/v0/postings/{co}?mode=json", timeout=30).json():
            add(j["hostedUrl"], j["text"], co, j["categories"].get("location", ""), j.get("workplaceType") == "remote",
                time.strftime("%Y-%m-%d", time.localtime(j["createdAt"] / 1000)), "lever", j["descriptionPlain"])
    for co in b.get("ashby") or []:
        for j in requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{co}", timeout=30).json()["jobs"]:
            add(j["jobUrl"], j["title"], co, j["location"], j["isRemote"], j["publishedAt"][:10], "ashby",
                j["descriptionPlain"])
    return jobs


def linkedin_description(url):
    page = requests.get(url, headers=UA, timeout=30).text
    m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.S)
    return strip_html(m.group(1)) if m else ""


def main(name):
    cfg, folder = person.load(name)
    seen_path = folder / "seen.json"
    seen = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
    inc, exc = person.words_pattern(cfg["title_include"]), person.words_pattern(cfg["title_exclude"])
    onsite = person.words_pattern(cfg["onsite_locations"])

    keep, keys = [], set()
    for j in board_jobs(cfg) + getonbrd_jobs(cfg) + jobspy_jobs(cfg):
        key = (j["title"].lower().strip(), j["company"].lower().strip())
        if (j["url"] in seen or "|".join(key) in seen or key in keys or not (j.get("junior") or inc.search(j["title"]))
                or exc.search(j["title"]) or not (j["remote"] or onsite.search(j["location"]))):
            continue
        keys.add(key)
        keep.append(j)

    for j in keep:
        if not j["description"] and j["source"] == "linkedin":
            j["description"] = linkedin_description(j["url"])
            time.sleep(2)

    keep = keep[:cfg["max_jobs_per_day"]]
    (folder / "new_jobs.json").write_text(json.dumps(keep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(keep)} new jobs -> {folder.name}/new_jobs.json")


if __name__ == "__main__":
    main(sys.argv[1])
