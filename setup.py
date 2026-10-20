"""Turn people/<name>/profile.md + searching.md into people/<name>/settings.yaml.

    python setup.py <name>            # generate settings.yaml (review it!)
    python setup.py <name> --upload   # store profile.md + settings.yaml as GitHub secrets
"""
import argparse
import subprocess

import yaml

import person

PROMPT = """You configure a daily job-search bot for the person below. From their profile and their
description of what they are looking for, write the bot's settings as YAML, exactly in this shape:

contact: {{name: "", location: "", phone: "", email: "", linkedin: "", github: ""}}  # "" when unknown
email_to: ""          # where to send the daily digest; the contact email unless they say otherwise
field: ""             # their professional field in a few words, e.g. "accounting / auditing"
home: ""              # city, country they live in
search_location: ""   # city to search in, e.g. "Buenos Aires, Argentina"
country: ""           # lowercase country name in English, e.g. "argentina"
search_terms: []      # 10-14 short job-board searches (2-3 words), in the languages jobs there are posted in,
                      #   covering the roles and seniority they want, e.g. "analista contable junior"
linkedin_terms: []    # exactly 2 LinkedIn boolean searches, e.g. (junior OR trainee) AND (contable OR accountant)
getonbrd_categories: []  # only for tech jobs: any of programming, data-science-analytics,
                         #   machine-learning-ai, sysadmin-devops-qa, cybersecurity; else []
boards: {{greenhouse: [], lever: [], ashby: []}}  # only companies they explicitly name and you know use these
title_include: []     # word stems a matching job TITLE contains (seniority + role words, both languages),
                      #   e.g. [junior, trainee, pasant, analista, contab, accountant]
title_exclude: []     # word stems that disqualify a title: too senior (senior, sr, lead, manager, gerente,
                      #   jefe, director...) and unrelated fields they don't want
onsite_locations: []  # lowercase places where on-site jobs are OK, e.g. [buenos aires, caba, capital federal]
education:            # their studies for the CV's fixed Education section, most important first, short
  en: [{{degree: "", school: "", dates: "", note: ""}}]
  es: [{{degree: "", school: "", dates: "", note: ""}}]
languages: {{en: "English (C1) · Spanish (native)", es: "Inglés (C1) · Español (nativo)"}}

Use ONLY facts from the profile for contact, education and languages; never invent.
Reply with ONLY the YAML, no prose, no code fences.

=== PROFILE ===
{profile}

=== WHAT THEY ARE LOOKING FOR ===
{searching}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("person")
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args()
    folder = person.ROOT / "people" / args.person

    if args.upload:
        for secret, file in (("PROFILE", "profile.md"), ("SETTINGS", "settings.yaml")):
            with open(folder / file, "rb") as f:
                subprocess.run(["gh", "secret", "set", f"{secret}_{args.person.upper()}"], stdin=f, check=True)
        print(f"Uploaded. Add '{args.person}' to the person list in .github/workflows/digest.yml")
        return

    prompt = PROMPT.format(profile=(folder / "profile.md").read_text(encoding="utf-8"),
                           searching=(folder / "searching.md").read_text(encoding="utf-8"))
    out = subprocess.run(["claude", "-p", "--model", "sonnet"], input=prompt, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    text = out.strip().removeprefix("```yaml").removeprefix("```").removesuffix("```").strip()
    yaml.safe_load(text)  # fail here, not tomorrow morning, if the YAML is broken
    (folder / "settings.yaml").write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {folder / 'settings.yaml'}. Review it, then run: python setup.py {args.person} --upload")


if __name__ == "__main__":
    main()
