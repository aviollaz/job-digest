"""For each job in people/<name>/new_jobs.json: score it, write a tailored CV PDF for good fits, write the digest."""
import argparse
import datetime
from html import escape as esc
import json
import os
import re
import subprocess
from pathlib import Path

from jinja2 import Template

import person

TEMPLATE = Template((person.ROOT / "cv_template.html").read_text(encoding="utf-8"))
CHROME = os.environ.get("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
LABELS = {
    "en": dict(summary="Summary", experience="Experience", projects="Projects", education="Education",
               skills="Skills", languages="Languages"),
    "es": dict(summary="Resumen", experience="Experiencia", projects="Proyectos", education="Educación",
               skills="Habilidades", languages="Idiomas"),
}

SCORE_PROMPT = """Rate how well the candidate below fits the job. The candidate works in {field}.
fit_score 0-10: seniority level, skills, field, location/remote. Be honest.
The candidate lives in {home}: score 2 or less if the job requires living or working
in another country (including "remote" roles restricted to another country).
Reply with ONLY a JSON object, no prose, no code fences:
{{"fit_score": int, "why": "one short sentence, max 20 words, in English", "lang": "language of the job posting: en|es"}}

=== CANDIDATE PROFILE ===
{profile}

=== JOB ===
Title: {title}
Company: {company}
Location: {location} (remote: {remote})

{description}
"""

CV_PROMPT = """You are an experienced {field} recruiter writing a one-page, ATS-friendly CV for the candidate
below, tailored to the job below. The profile is raw notes: do NOT copy its sentences. Rewrite everything
the way a polished CV reads: concise, confident, elegant.

Writing style:
- Bullets start with a strong past-tense verb (Built, Managed, Reconciled, Automated, Prepared...) and say what
  was done and why it matters. Each bullet must fit on ONE line: max 15 words. No filler ("very detailed", "in a way that").
- Give roles and projects short, professional names; role, org and project names max 6 words each.
  Self-employment org is "Self-employed" / "Independiente". Keep the real dates.
- Keep each item in its own section: anything the profile lists as a personal project goes ONLY in projects,
  never inside a job's bullets. If the profile has no projects, return an empty projects list.
- Summary: 2 sentences, specific to this job, no clichés ("passionate", "team player", "fast learner").
  Don't repeat education details (% completed, degree titles); they are shown separately.
- Use the job's keywords where they truthfully describe the candidate's work, so ATS matching works.
- Choose what to include: the 2-3 projects most relevant to this job, 1-3 bullets per entry. It must fit on one page.
- Skills: 3-4 categories, most relevant first, only skills/tools the profile mentions. Never name a category
  "Languages"/"Idiomas"/"Lenguajes"; spoken languages and education are added separately.

Hard rule: never invent experience, tools, metrics or dates, and never turn the job's requirements into
claims about the candidate (no "strong foundation in X" / "base sólida en X" unless the profile says it).
No claims about habits, frequency or scale ("daily", "production", "at scale") that the profile doesn't state.
Rephrase freely, but every fact must come from the profile.

Write the CV in {lang_name}. Reply with ONLY a JSON object, no prose, no code fences:
{{"headline": "short role-oriented title", "summary": "",
 "experience": [{{"title": "", "org": "", "dates": "", "bullets": [""]}}],
 "projects": [{{"name": "", "tech": "tools/skills used, comma separated, max 6", "bullets": [""]}}],
 "skills": [{{"category": "", "items": "comma separated"}}]}}

=== CANDIDATE PROFILE ===
{profile}

=== JOB ===
Title: {title}
Company: {company}
Location: {location} (remote: {remote})

{description}
"""


def ask_claude(model, prompt, job, **extra):
    prompt = prompt.format(**{**job, "description": job["description"][:12000]}, **extra)
    out = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json"],
                         input=prompt, capture_output=True, text=True, encoding="utf-8", check=True)
    text = json.loads(out.stdout)["result"]
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def render_pdf(cfg, cv, path):
    html_path = path.with_suffix(".html")
    lang = cv["lang"]
    labels = {**LABELS[lang], **(cfg.get("labels") or {}).get(lang, {})}
    html_path.write_text(TEMPLATE.render({**cfg["contact"], **cv, "labels": labels,
                                          "education": cfg["education"][lang], "languages": cfg["languages"][lang]}),
                         encoding="utf-8")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                    f"--print-to-pdf={path}", html_path.as_uri()], capture_output=True, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("person")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    cfg, folder = person.load(args.person)
    ctx = dict(profile=(folder / "profile.md").read_text(encoding="utf-8"), field=cfg["field"], home=cfg["home"])
    jobs = json.loads((folder / "new_jobs.json").read_text(encoding="utf-8"))[:args.limit]
    seen_path = folder / "seen.json"
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else []
    out_dir = person.ROOT / "out" / args.person / datetime.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, job in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {job['title']} @ {job['company']}")
        try:
            score = ask_claude("haiku", SCORE_PROMPT, job, **ctx)
            job.update(score=score["fit_score"], why=score["why"], pdf=None)
            if score["fit_score"] >= cfg["min_fit_score"]:
                lang = "es" if score["lang"] == "es" else "en"
                cv = ask_claude("sonnet", CV_PROMPT, job, **ctx, lang_name={"es": "Spanish", "en": "English"}[lang])
                name = re.sub(r"[^\w]+", "_", f"{job['company']}_{job['title']}").strip("_")[:80]
                job["pdf"] = out_dir / f"{name}.pdf"
                render_pdf(cfg, {**cv, "lang": lang}, job["pdf"])
        except Exception as e:
            print(f"  failed: {e}")
            continue
        results.append(job)
        seen += [job["url"], f"{job['title'].lower().strip()}|{job['company'].lower().strip()}"]
        seen_path.write_text(json.dumps(seen))

    results.sort(key=lambda j: -j["score"])
    rows = []
    for j in [j for j in results if j["score"] >= cfg["min_show_score"]]:
        where = "Remote" if j["remote"] else esc(j["location"])
        cv = f'<a href="{j["pdf"].name}">CV</a>' if j["pdf"] else "low fit"
        rows.append(f'<tr><td>{j["score"]}</td><td><a href="{esc(j["url"])}">{esc(j["title"])}</a><br>'
                    f'<small>{esc(j["company"])} · {where} · {j["source"]} · {j["posted"]}</small></td>'
                    f'<td>{esc(j["why"])}</td><td>{cv}</td></tr>')
    (out_dir / "digest.html").write_text(
        f'<!doctype html><meta charset="utf-8"><title>Jobs {out_dir.name}</title>'
        '<style>body{font-family:Segoe UI,sans-serif;margin:24px}td{padding:8px;border-bottom:1px solid #ddd;'
        'vertical-align:top}small{color:#666}</style>'
        f'<h1>Jobs {out_dir.name}</h1><p>{len(results)} new jobs scored, {len(rows)} shown (score ≥ '
        f'{cfg["min_show_score"]}).</p><table>{"".join(rows)}</table>', encoding="utf-8")
    print(f"digest -> {out_dir / 'digest.html'}")


if __name__ == "__main__":
    main()
