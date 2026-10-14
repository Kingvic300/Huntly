"""CV and cover-letter generation (DOCX + PDF).

Rule: never invent content. Tailoring here means *selecting and ordering* facts
already in the profile by relevance to the job. When the optional LLM drafts
cover-letter prose, :func:`find_fabrications` rejects any paragraph that
introduces numbers, proper nouns or skills that do not appear in the profile or
the job posting's company/title; rejected drafts fall back to a template built
purely from profile facts.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor
from fpdf import FPDF

from huntly.config import TZ, resource_path
from huntly.services.matching import _term_regex
from huntly.services.profile import Experience, ProfileData, profile_corpus

ALLOWED_UPLOAD_TYPES = {
    "pdf": (b"%PDF-",),
    "docx": (b"PK\x03\x04",),
}


@dataclass
class TailoredCV:
    profile: ProfileData
    skills: list[str]
    experience: list[Experience]
    relevant_skills: list[str]
    summary_override: str | None = None


def _relevance(text: str, job_text: str) -> int:
    jt = job_text.lower()
    words = {w for w in re.findall(r"[a-z][a-z0-9+#.]{2,}", text.lower())}
    return sum(1 for w in words if _term_regex(w).search(jt))


def tailor(profile: ProfileData, job_title: str, job_text: str) -> TailoredCV:
    full = f"{job_title}\n{job_text}"
    relevant = [s for s in profile.skills if _term_regex(s).search(full.lower())]
    others = [s for s in profile.skills if s not in relevant]
    experience = []
    for e in profile.experience:
        highlights = sorted(e.highlights, key=lambda h: -_relevance(h, full))
        experience.append(e.model_copy(update={"highlights": highlights}))
    return TailoredCV(profile=profile, skills=relevant + others, experience=experience, relevant_skills=relevant)


# --- anti-fabrication ------------------------------------------------------
_NUMBER = re.compile(r"\d[\d,.%]*")
_PROPER = re.compile(r"\b[A-Z][a-zA-Z0-9&.+#-]{2,}(?:\s+[A-Z][a-zA-Z0-9&.+#-]{2,})*")
_COMMON = {
    "I", "My", "The", "This", "That", "These", "With", "As", "In", "At", "For", "And", "But", "Our", "Your", "You",
    "We", "It", "Its", "Thank", "Thanks", "Dear", "Hiring", "Manager", "Team", "Sincerely", "Regards", "Best",
    "Throughout", "Having", "During", "While", "Over", "Since", "When", "Where", "Through", "Additionally",
    "Furthermore", "Moreover", "Also", "Please", "Looking", "Given", "Recently", "Currently", "Previously",
    "Today", "Role", "Position", "Company", "Kind", "Warm", "Yours", "Here", "There", "What", "Why", "How",
    "API", "APIs", "CV", "Thank you",
}


def find_fabrications(text: str, allowed_corpus: str) -> list[str]:
    corpus = allowed_corpus.lower()
    problems = []
    for n in _NUMBER.findall(text):
        n = n.rstrip(".,")
        if n and n.lower() not in corpus:
            problems.append(n)
    for m in _PROPER.findall(text):
        for w in m.split():
            w = w.strip(".,;:")
            if w and w not in _COMMON and w.lower() not in corpus:
                problems.append(w)
    return sorted(set(problems))


_PAST_VERBS = {"built", "led", "ran", "wrote", "made", "grew", "cut", "won", "set", "drove", "took", "began"}


def _as_clause(highlight: str) -> str:
    """'Built REST APIs' -> 'I built REST APIs' (only for verb-led achievements)."""
    first = highlight.split(" ", 1)[0]
    if first.lower().endswith("ed") or first.lower() in _PAST_VERBS:
        return "I " + first.lower() + highlight[len(first):]
    return highlight


def template_paragraphs(t: TailoredCV, job_title: str, company: str) -> list[str]:
    p = t.profile
    paras = []
    intro = f"I am writing to apply for the {job_title} role" + (f" at {company}" if company else "") + "."
    if p.headline:
        article = "an" if p.headline[:1].lower() in "aeiou" else "a"
        intro += f" I am {article} {p.headline}."
    paras.append(intro)
    if t.relevant_skills:
        skills = t.relevant_skills[:8]
        listed = ", ".join(skills[:-1]) + f" and {skills[-1]}" if len(skills) > 1 else skills[0]
        paras.append(f"The role calls for {listed}, {'all of which I use' if len(skills) > 1 else 'which I use'} in my work.")
    if t.experience:
        e = t.experience[0]
        if e.title and e.company:
            line = f"In my role as {e.title} at {e.company}"
            line += f", {_as_clause(e.highlights[0]).rstrip('.')}." if e.highlights else ", I have built on these skills every day."
            paras.append(line)
    if p.summary:
        paras.append(p.summary)
    paras.append("I would welcome the chance to discuss how I can contribute to your team.")
    return paras


# --- rendering -------------------------------------------------------------
# Layout rules for ATS parsers: one column, no tables/images/text boxes, standard
# headings in a fixed order, contact details as plain text at the top, real text
# (never images), and dates on the same line as each role.
HEADINGS = {
    "summary": "Summary",
    "skills": "Skills",
    "experience": "Work Experience",
    "projects": "Projects",
    "education": "Education",
    "certifications": "Certifications",
    "languages": "Languages",
}


def _contact_line(p: ProfileData) -> str:
    return " | ".join(x for x in [p.email, p.phone, p.location] if x)


def _links_line(p: ProfileData) -> str:
    from huntly.services.profile import contact_links

    return " | ".join(contact_links(p))


def _dates(start: str, end: str) -> str:
    return " - ".join(x for x in [start, end] if x)


def _summary(t: TailoredCV) -> str:
    return t.summary_override or t.profile.summary


def cv_plaintext(t: TailoredCV) -> str:
    """The CV's text exactly as an ATS would read it (used for the keyword check)."""
    p = t.profile
    out = [p.full_name, p.headline, _contact_line(p), _links_line(p)]
    if _summary(t):
        out += [HEADINGS["summary"], _summary(t)]
    if t.skills:
        out += [HEADINGS["skills"], ", ".join(t.skills)]
    for e in t.experience:
        out += [e.title, e.company, e.location, _dates(e.start, e.end), *e.highlights]
    for pr in p.projects:
        out += [pr.name, pr.description, ", ".join(pr.technologies)]
    for ed in p.education:
        out += [ed.qualification, ed.institution, ed.details]
    out += p.certifications + p.languages
    return "\n".join(x for x in out if x)


def _docx_heading(doc, text: str) -> None:
    h = doc.add_heading(text, level=1)
    for run in h.runs:
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0x1F, 0x24, 0x2E)
        run.font.name = "Calibri"


def render_cv_docx(t: TailoredCV, path: Path) -> None:
    p = t.profile
    doc = DocxDocument()
    doc.core_properties.title = f"{p.full_name} CV"
    doc.core_properties.author = p.full_name
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    name = doc.add_paragraph()
    r = name.add_run(p.full_name or "Your Name")
    r.bold = True
    r.font.size = Pt(18)
    if p.headline:
        doc.add_paragraph(p.headline)
    for line in (_contact_line(p), _links_line(p)):
        if line:
            doc.add_paragraph(line)
    if _summary(t):
        _docx_heading(doc, HEADINGS["summary"])
        doc.add_paragraph(_summary(t))
    if t.skills:
        _docx_heading(doc, HEADINGS["skills"])
        doc.add_paragraph(", ".join(t.skills))
    if t.experience:
        _docx_heading(doc, HEADINGS["experience"])
        for e in t.experience:
            para = doc.add_paragraph()
            para.add_run(", ".join(x for x in [e.title, e.company] if x)).bold = True
            meta = " | ".join(x for x in [e.location, _dates(e.start, e.end)] if x)
            if meta:
                para.add_run(f"\n{meta}")
            for h in e.highlights:
                doc.add_paragraph(h, style="List Bullet")
    if p.projects:
        _docx_heading(doc, HEADINGS["projects"])
        for pr in p.projects:
            para = doc.add_paragraph()
            para.add_run(pr.name).bold = True
            if pr.description:
                para.add_run(f": {pr.description}")
            if pr.technologies:
                para.add_run(f" ({', '.join(pr.technologies)})")
            if pr.url:
                para.add_run(f" {pr.url}")
    if p.education:
        _docx_heading(doc, HEADINGS["education"])
        for ed in p.education:
            para = doc.add_paragraph()
            para.add_run(", ".join(x for x in [ed.qualification, ed.institution] if x)).bold = True
            if ed.start or ed.end:
                para.add_run(f"\n{_dates(ed.start, ed.end)}")
            if ed.details:
                doc.add_paragraph(ed.details)
    if p.certifications:
        _docx_heading(doc, HEADINGS["certifications"])
        for c in p.certifications:
            doc.add_paragraph(c, style="List Bullet")
    if p.languages:
        _docx_heading(doc, HEADINGS["languages"])
        doc.add_paragraph(", ".join(p.languages))
    doc.save(path)


def render_letter_docx(p: ProfileData, paragraphs: list[str], company: str, path: Path) -> None:
    doc = DocxDocument()
    doc.core_properties.author = p.full_name
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    doc.add_paragraph(p.full_name)
    for line in (_contact_line(p), _links_line(p)):
        if line:
            doc.add_paragraph(line)
    doc.add_paragraph(datetime.now(TZ).strftime("%d %B %Y"))
    doc.add_paragraph(f"Dear {company + ' ' if company else ''}Hiring Team,")
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.add_paragraph(f"Kind regards,\n{p.full_name}")
    doc.save(path)


class _Pdf(FPDF):
    def __init__(self, title: str = "", author: str = ""):
        super().__init__(format="A4")
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, 16)
        self.set_title(title)
        self.set_author(author)
        self.set_creator("Huntly")
        regular = resource_path("assets", "fonts", "DejaVuSans.ttf")
        bold = resource_path("assets", "fonts", "DejaVuSans-Bold.ttf")
        self.add_font("Body", "", str(regular))
        self.add_font("Body", "B", str(bold))
        self.add_page()

    def text_block(self, text: str, size: float = 10, style: str = "", gap: float = 1.5, color=(25, 28, 34)) -> None:
        self.set_font("Body", style, size)
        self.set_text_color(*color)
        self.multi_cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(gap)

    def heading(self, text: str) -> None:
        self.ln(2)
        self.text_block(text, 11.5, "B", 0.8)
        self.set_draw_color(190, 195, 205)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)


def render_cv_pdf(t: TailoredCV, path: Path) -> int:
    p = t.profile
    pdf = _Pdf(f"{p.full_name} CV", p.full_name)
    pdf.text_block(p.full_name or "Your Name", 18, "B", 0.5)
    if p.headline:
        pdf.text_block(p.headline, 11, "", 0.8, (60, 64, 72))
    for line in (_contact_line(p), _links_line(p)):
        if line:
            pdf.text_block(line, 9.5, "", 0.5, (60, 64, 72))
    pdf.ln(1)
    if _summary(t):
        pdf.heading(HEADINGS["summary"])
        pdf.text_block(_summary(t))
    if t.skills:
        pdf.heading(HEADINGS["skills"])
        pdf.text_block(", ".join(t.skills))
    if t.experience:
        pdf.heading(HEADINGS["experience"])
        for e in t.experience:
            pdf.text_block(", ".join(x for x in [e.title, e.company] if x), 10.5, "B", 0)
            meta = " | ".join(x for x in [e.location, _dates(e.start, e.end)] if x)
            if meta:
                pdf.text_block(meta, 9.5, "", 0.6, (80, 84, 92))
            for h in e.highlights:
                pdf.text_block(f"•  {h}", 10, "", 0.3)
            pdf.ln(1.5)
    if p.projects:
        pdf.heading(HEADINGS["projects"])
        for pr in p.projects:
            line = pr.name + (f": {pr.description}" if pr.description else "")
            if pr.technologies:
                line += f" ({', '.join(pr.technologies)})"
            if pr.url:
                line += f" {pr.url}"
            pdf.text_block(line)
    if p.education:
        pdf.heading(HEADINGS["education"])
        for ed in p.education:
            pdf.text_block(", ".join(x for x in [ed.qualification, ed.institution] if x), 10.5, "B", 0)
            if ed.start or ed.end:
                pdf.text_block(_dates(ed.start, ed.end), 9.5, "", 0.4, (80, 84, 92))
            if ed.details:
                pdf.text_block(ed.details)
    if p.certifications:
        pdf.heading(HEADINGS["certifications"])
        for c in p.certifications:
            pdf.text_block(f"•  {c}", 10, "", 0.3)
    if p.languages:
        pdf.heading(HEADINGS["languages"])
        pdf.text_block(", ".join(p.languages))
    pdf.output(str(path))
    return pdf.page_no()


def render_letter_pdf(p: ProfileData, paragraphs: list[str], company: str, path: Path) -> None:
    pdf = _Pdf(f"{p.full_name} cover letter", p.full_name)
    pdf.text_block(p.full_name, 14, "B", 0.5)
    for line in (_contact_line(p), _links_line(p)):
        if line:
            pdf.text_block(line, 9.5, "", 0.5, (60, 64, 72))
    pdf.ln(3)
    pdf.text_block(datetime.now(TZ).strftime("%d %B %Y"), 10, "", 4)
    pdf.text_block(f"Dear {company + ' ' if company else ''}Hiring Team,", 10.5, "", 3)
    for para in paragraphs:
        pdf.text_block(para, 10.5, "", 3)
    pdf.text_block(f"Kind regards,\n{p.full_name}", 10.5)
    pdf.output(str(path))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_filename(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")
    return (s or "document")[:limit]


def detect_upload_type(head: bytes, filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    magics = ALLOWED_UPLOAD_TYPES.get(ext)
    if magics and any(head.startswith(m) for m in magics):
        return ext
    return None


def allowed_corpus_for_letter(p: ProfileData, job_title: str, company: str) -> str:
    return f"{profile_corpus(p)}\n{job_title}\n{company}"
