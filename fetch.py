"""Fetch fresh junior/intern postings, filter them, and write new_jobs.json."""
import html
import json
import re
import time
from pathlib import Path

import requests
import yaml
from jobspy import scrape_jobs

ROOT = Path(__file__).parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}


def strip_html(s):
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def jobspy_jobs():
    jobs = []
    searches = [dict(search_term=t, location="Buenos Aires, Argentina", country_indeed="argentina",
                     site_name=["indeed"]) for t in CFG["search_terms"]]
    for t in CFG["linkedin_terms"]:
        searches += [dict(search_term=t, location="Buenos Aires, Argentina", site_name=["linkedin"]),
                     dict(search_term=t, location="Argentina", is_remote=True, site_name=["linkedin"])]
    for s in searches:
        try:
            df = scrape_jobs(results_wanted=CFG["results_per_search"], hours_old=CFG["hours_old"], verbose=0, **s)
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


def getonbrd_jobs():
    jobs, companies = [], {}
    cutoff = time.time() - CFG["hours_old"] * 3600
    for term in CFG["search_terms"]:
        data = requests.get("https://www.getonbrd.com/api/v0/search/jobs",
                            params={"query": term, "per_page": 50}, timeout=30).json()["data"]
        for j in data:
            a = j["attributes"]
            remote = a["remote_modality"] == "fully_remote"
            if a["published_at"] < cutoff or not (remote or "Argentina" in a["countries"]):
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
            })
    return jobs


def board_jobs():
    jobs, b = [], CFG["boards"]

    def add(url, title, company, location, remote, posted, source, description):
        remote = remote or "remote" in location.lower()
        jobs.append(dict(url=url, title=title, company=company, location=location, remote=remote,
                         posted=posted, source=source, description=description))

    for co in b["greenhouse"]:
        for j in requests.get(f"https://boards-api.greenhouse.io/v1/boards/{co}/jobs?content=true", timeout=30).json()["jobs"]:
            add(j["absolute_url"], j["title"], j.get("company_name") or co, j["location"]["name"], False,
                j["updated_at"][:10], "greenhouse", strip_html(html.unescape(j["content"])))
    for co in b["lever"]:
        for j in requests.get(f"https://api.lever.co/v0/postings/{co}?mode=json", timeout=30).json():
            add(j["hostedUrl"], j["text"], co, j["categories"].get("location", ""), j.get("workplaceType") == "remote",
                time.strftime("%Y-%m-%d", time.localtime(j["createdAt"] / 1000)), "lever", j["descriptionPlain"])
    for co in b["ashby"]:
        for j in requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{co}", timeout=30).json()["jobs"]:
            add(j["jobUrl"], j["title"], co, j["location"], j["isRemote"], j["publishedAt"][:10], "ashby",
                j["descriptionPlain"])
    return jobs


def linkedin_description(url):
    page = requests.get(url, headers=UA, timeout=30).text
    m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.S)
    return strip_html(m.group(1)) if m else ""


def main():
    seen = set(json.loads((ROOT / "seen.json").read_text())) if (ROOT / "seen.json").exists() else set()
    inc, exc = re.compile(CFG["title_include"], re.I), re.compile(CFG["title_exclude"], re.I)
    onsite = re.compile(CFG["onsite_locations"], re.I)

    keep, keys = [], set()
    for j in board_jobs() + getonbrd_jobs() + jobspy_jobs():
        key = (j["title"].lower().strip(), j["company"].lower().strip())
        if (j["url"] in seen or key in keys or not inc.search(j["title"]) or exc.search(j["title"])
                or not (j["remote"] or onsite.search(j["location"]))):
            continue
        keys.add(key)
        keep.append(j)

    for j in keep:
        if not j["description"] and j["source"] == "linkedin":
            j["description"] = linkedin_description(j["url"])
            time.sleep(2)

    keep = keep[:CFG["max_jobs_per_day"]]
    (ROOT / "new_jobs.json").write_text(json.dumps(keep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(keep)} new jobs -> new_jobs.json")


if __name__ == "__main__":
    main()
