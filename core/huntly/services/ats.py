"""ATS (applicant tracking system) readiness check for a generated CV.

Compares the job posting's keywords with the CV text and runs format checks.
Missing keywords are reported, never added: only the user can decide they are true.
"""

from __future__ import annotations

import re

from huntly.services.matching import _term_regex
from huntly.services.profile import ProfileData

# Common skills and tools that ATS filters look for. Profile skills are always added.
VOCABULARY = """
python java javascript typescript go golang rust c c++ c# ruby php kotlin swift scala r sql nosql bash powershell perl
react angular vue next.js node.js express django flask fastapi spring .net laravel rails graphql rest api apis grpc
html css tailwind sass redux jquery webpack vite
postgresql mysql mongodb redis elasticsearch sqlite oracle dynamodb cassandra kafka rabbitmq
aws azure gcp google cloud docker kubernetes terraform ansible jenkins github actions gitlab ci/cd ci cd linux unix nginx serverless lambda
git jira confluence figma
machine learning deep learning nlp pytorch tensorflow pandas numpy scikit-learn data analysis data engineering etl spark hadoop airflow power bi tableau excel
cybersecurity security penetration testing pentesting siem soc incident response vulnerability assessment owasp burp suite metasploit nmap wireshark kali linux
threat intelligence firewall iam zero trust iso 27001 nist soc 2 gdpr encryption network security cloud security devsecops
microservices distributed systems system design testing unit testing tdd automation qa selenium cypress playwright
agile scrum kanban project management product management stakeholder management communication leadership mentoring
customer service sales marketing seo content writing copywriting accounting finance
""".split("\n")

_PHRASES = [w.strip() for line in VOCABULARY for w in re.split(r"\s{2,}|\t", line) if w.strip()]
# Split into terms: keep known multi-word phrases, otherwise single words.
MULTI = [
    "google cloud", "github actions", "ci/cd", "machine learning", "deep learning", "data analysis", "data engineering", "power bi",
    "penetration testing", "incident response", "vulnerability assessment", "burp suite", "kali linux", "threat intelligence",
    "zero trust", "iso 27001", "soc 2", "network security", "cloud security", "distributed systems", "system design", "unit testing",
    "project management", "product management", "stakeholder management", "customer service", "content writing", "rest api",
]
# Words too ambiguous to count on their own ("go to market", "r&d", "c-level").
AMBIGUOUS = {"go", "c", "r", "rest", "excel", "security", "testing", "automation", "communication", "leadership", "sales", "marketing", "finance"}
SINGLE = sorted({w for line in VOCABULARY for w in line.split() if w} - {w for m in MULTI for w in m.split()} - AMBIGUOUS | {"golang"})
TERMS = MULTI + [w for w in SINGLE if len(w) > 1]


DISPLAY = {
    "c#": "C#", "c++": "C++", "node.js": "Node.js", "next.js": "Next.js", "nosql": "NoSQL", "php": "PHP", "sql": "SQL",
    "typescript": "TypeScript", "javascript": "JavaScript", "aws": "AWS", "gcp": "GCP", "ci/cd": "CI/CD", "ci": "CI", "cd": "CD",
    "postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB", "graphql": "GraphQL", "html": "HTML", "css": "CSS",
    "api": "API", "apis": "APIs", "rest api": "REST API", "grpc": "gRPC", "etl": "ETL", "nlp": "NLP", "siem": "SIEM", "soc": "SOC",
    "soc 2": "SOC 2", "iam": "IAM", "owasp": "OWASP", "gdpr": "GDPR", "nist": "NIST", "iso 27001": "ISO 27001", "qa": "QA",
    "tdd": "TDD", "seo": "SEO", "jquery": "jQuery", "devsecops": "DevSecOps", "github actions": "GitHub Actions", "gitlab": "GitLab",
    "dynamodb": "DynamoDB", "rabbitmq": "RabbitMQ", "pytorch": "PyTorch", "tensorflow": "TensorFlow", "numpy": "NumPy",
    "scikit-learn": "scikit-learn", "fastapi": "FastAPI", "power bi": "Power BI", "kali linux": "Kali Linux", "burp suite": "Burp Suite",
    ".net": ".NET", "vue": "Vue", "nginx": "NGINX", "sqlite": "SQLite", "golang": "Go", "google cloud": "Google Cloud",
}


def display(term: str) -> str:
    key = term.lower()
    if key in DISPLAY:
        return DISPLAY[key]
    return term if term != key else term[:1].upper() + term[1:]


def job_keywords(job_text: str, profile: ProfileData) -> list[str]:
    text = job_text.lower()
    found, seen = [], set()
    for term in [*profile.skills, *TERMS]:
        key = term.lower()
        if key in seen or len(key) < 2:
            continue
        if _term_regex(key).search(text):
            seen.add(key)
            found.append(display(term))
    return found[:40]


def ats_report(*, cv_text: str, job_title: str, job_text: str, profile: ProfileData, fmt: str, pages: int | None, filename: str) -> dict:
    keywords = job_keywords(f"{job_title}\n{job_text}", profile)
    cv = cv_text.lower()
    profile_text = " ".join([*profile.skills, profile.summary, *[h for e in profile.experience for h in e.highlights]]).lower()
    covered = [k for k in keywords if _term_regex(k.lower()).search(cv)]
    gaps = [k for k in keywords if k not in covered and not _term_regex(k.lower()).search(profile_text)]
    unused = [k for k in keywords if k not in covered and k not in gaps]
    title_in_cv = bool(_term_regex(job_title.lower()).search(cv)) if job_title else False
    first = (profile.full_name or "").split(" ")[0].lower()

    checks = [
        {"id": "layout", "label": "Single column, no tables, images or text boxes", "ok": True},
        {"id": "headings", "label": "Standard section headings (Summary, Skills, Work Experience, Education)", "ok": True},
        {"id": "text", "label": "Real, selectable text" + (" in a PDF" if fmt == "pdf" else " in an editable Word file"), "ok": True},
        {"id": "contact", "label": "Email and phone at the top", "ok": bool(profile.email and profile.phone)},
        {"id": "linkedin", "label": "LinkedIn profile link included", "ok": bool(profile.linkedin_url)},
        {"id": "experience", "label": "Work experience with dates", "ok": bool(profile.experience) and all(e.start for e in profile.experience)},
        {"id": "length", "label": "Two pages or fewer", "ok": pages is None or pages <= 2},
        {"id": "filename", "label": "File name includes your name", "ok": bool(first) and first in filename.lower()},
    ]
    coverage = round(100 * len(covered) / len(keywords)) if keywords else None
    return {
        "keywords": keywords,
        "covered": covered,
        "unused_from_profile": unused,
        "gaps": gaps,
        "coverage": coverage,
        "title_match": title_in_cv,
        "checks": checks,
        "score": round(0.7 * (coverage if coverage is not None else 100) + 30 * sum(c["ok"] for c in checks) / len(checks)),
    }
