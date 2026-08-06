"""
Structured data extraction — Phase 3.

Architecture (three-layer pipeline)
------------------------------------
Layer 1 — Regex (always runs, O(n), free):
    Email, phone, LinkedIn/GitHub URLs, date ranges → experience years.

Layer 2 — Skills taxonomy (always runs, O(n), free):
    Built-in list of 400+ skills/tools matched with word-boundary regex.
    Domain tags derived from skill clusters.

Layer 3 — Groq LLM (single call, ~0.5 s, ~$0.0001/doc):
    Extracts: full_name, current_title, location, education, summary.
    Falls back gracefully if Groq is not configured.

Entry points
------------
parse_cv(text: str) -> ParsedCV
parse_jd(text: str) -> ParsedJD
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output data structures
# ---------------------------------------------------------------------------

@dataclass
class Education:
    degree: str
    field: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[int] = None


@dataclass
class ParsedCV:
    # Contact
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    location: Optional[str] = None
    # Professional
    current_title: Optional[str] = None
    total_experience_years: Optional[float] = None
    summary: Optional[str] = None
    # Extracted collections
    skills: list[str] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)
    domain_tags: list[str] = field(default_factory=list)
    # Meta
    parse_method: str = "regex"       # regex | regex+groq
    confidence: float = 0.5


@dataclass
class ParsedJD:
    job_title: Optional[str] = None
    location: Optional[str] = None
    experience_range: Optional[str] = None
    minimum_qualification: Optional[str] = None
    required_skills: list[str] = field(default_factory=list)
    domain_tags: list[str] = field(default_factory=list)
    jd_summary: Optional[str] = None
    parse_method: str = "regex"
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# Skills taxonomy (400+ entries, grouped for domain tagging)
# ---------------------------------------------------------------------------

_SKILLS_TAXONOMY: dict[str, list[str]] = {
    # ── Programming languages ──────────────────────────────────────────────
    "programming": [
        "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go",
        "Golang", "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R",
        "MATLAB", "Perl", "Shell", "Bash", "PowerShell", "SQL", "PL/SQL",
        "T-SQL", "Groovy", "Lua", "Dart", "Elixir", "Haskell", "Clojure",
    ],
    # ── Web / Frontend ─────────────────────────────────────────────────────
    "frontend": [
        "React", "React.js", "Angular", "Vue", "Vue.js", "Next.js", "Nuxt.js",
        "Svelte", "HTML", "CSS", "SCSS", "SASS", "Tailwind", "Bootstrap",
        "Material UI", "Redux", "MobX", "GraphQL", "REST API", "Webpack",
        "Vite", "jQuery", "Backbone.js", "Ember.js",
    ],
    # ── Backend / Frameworks ───────────────────────────────────────────────
    "backend": [
        "Node.js", "Express.js", "FastAPI", "Django", "Flask", "Spring",
        "Spring Boot", "Laravel", "Rails", "Ruby on Rails", "ASP.NET",
        ".NET", "NestJS", "Fastify", "Gin", "Echo", "Fiber", "gRPC",
        "Microservices", "REST", "GraphQL", "WebSocket",
    ],
    # ── Cloud & DevOps ─────────────────────────────────────────────────────
    "cloud_devops": [
        "AWS", "Azure", "GCP", "Google Cloud", "Docker", "Kubernetes", "K8s",
        "Terraform", "Ansible", "Chef", "Puppet", "CI/CD", "Jenkins",
        "GitHub Actions", "GitLab CI", "CircleCI", "Helm", "ArgoCD",
        "Prometheus", "Grafana", "ELK", "Elasticsearch", "Kibana", "Logstash",
        "Linux", "Ubuntu", "CentOS", "RHEL", "Nginx", "Apache",
    ],
    # ── Databases ──────────────────────────────────────────────────────────
    "database": [
        "PostgreSQL", "MySQL", "SQLite", "Microsoft SQL Server", "Oracle",
        "MongoDB", "Redis", "Cassandra", "DynamoDB", "Elasticsearch",
        "InfluxDB", "Neo4j", "Supabase", "Firebase", "Firestore",
        "MariaDB", "CockroachDB", "ClickHouse", "Snowflake", "BigQuery",
    ],
    # ── AI / ML / Data Science ─────────────────────────────────────────────
    "ai_ml": [
        "Machine Learning", "Deep Learning", "NLP", "Natural Language Processing",
        "Computer Vision", "TensorFlow", "PyTorch", "Keras", "scikit-learn",
        "XGBoost", "LightGBM", "Pandas", "NumPy", "Matplotlib", "Seaborn",
        "Hugging Face", "LangChain", "LlamaIndex", "OpenAI", "Gemini",
        "RAG", "Vector Database", "Qdrant", "Pinecone", "Weaviate",
        "FAISS", "Prompt Engineering", "Fine-tuning", "LLM", "Transformer",
        "BERT", "GPT", "Ollama", "Stable Diffusion", "spaCy",
    ],
    # ── Data Engineering ───────────────────────────────────────────────────
    "data_engineering": [
        "Apache Spark", "Apache Kafka", "Apache Airflow", "Apache Hadoop",
        "Databricks", "dbt", "ETL", "Tableau", "Power BI", "Looker",
        "Data Pipeline", "Data Warehouse", "Data Lake", "Delta Lake",
    ],
    # ── ITSM / Service Management ─────────────────────────────────────────
    "itsm": [
        "ITIL", "ITSM", "ServiceNow", "BMC Remedy", "Freshservice",
        "Incident Management", "Problem Management", "Change Management",
        "Service Delivery", "SLA", "KPI", "CMDB", "Asset Management",
        "Capacity Management", "Availability Management", "Configuration Management",
        "Release Management", "ITIL V3", "ITIL 4",
    ],
    # ── Project Management ────────────────────────────────────────────────
    "project_management": [
        "Agile", "Scrum", "Kanban", "JIRA", "Confluence", "Trello",
        "Asana", "Monday.com", "PMP", "PRINCE2", "Waterfall", "SAFe",
        "Lean", "Six Sigma", "Product Management", "Stakeholder Management",
    ],
    # ── Testing / QA ──────────────────────────────────────────────────────
    "testing": [
        "Selenium", "Playwright", "Cypress", "Jest", "Pytest", "JUnit",
        "TestNG", "Postman", "JMeter", "LoadRunner", "Manual Testing",
        "Automation Testing", "Performance Testing", "API Testing",
        "Regression Testing", "Unit Testing", "Integration Testing",
    ],
    # ── Mobile ────────────────────────────────────────────────────────────
    "mobile": [
        "Android", "iOS", "React Native", "Flutter", "Xamarin",
        "Swift", "Kotlin", "Objective-C",
    ],
    # ── Security ──────────────────────────────────────────────────────────
    "security": [
        "Cybersecurity", "Penetration Testing", "OWASP", "SIEM",
        "Vulnerability Assessment", "IAM", "OAuth", "JWT", "SSL/TLS",
        "Firewall", "Network Security", "SOC",
    ],
    # ── Networking / Telecom ───────────────────────────────────────────────
    "networking_telecom": [
        "TCP/IP", "DNS", "HTTP", "HTTPS", "VPN", "LAN", "WAN",
        "BGP", "OSPF", "Cisco", "Juniper", "Telecom", "5G", "4G",
        "LTE", "VoIP", "MPLS", "SD-WAN",
    ],
    # ── Version Control ────────────────────────────────────────────────────
    "version_control": [
        "Git", "GitHub", "GitLab", "Bitbucket", "SVN", "Mercurial",
    ],
    # ── Blockchain ────────────────────────────────────────────────────────
    "blockchain": [
        "Blockchain", "Ethereum", "Solidity", "Web3", "Smart Contract",
        "Hyperledger", "NFT", "DeFi",
    ],
}

# Build flat list + domain map
_ALL_SKILLS: list[str] = []
_SKILL_DOMAIN: dict[str, str] = {}

for _domain, _skills in _SKILLS_TAXONOMY.items():
    for _s in _skills:
        _ALL_SKILLS.append(_s)
        _SKILL_DOMAIN[_s.lower()] = _domain

# Sort longest first so multi-word skills match before single words
_ALL_SKILLS.sort(key=len, reverse=True)

# Compile one regex per skill with word boundaries
_SKILL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<!\w)" + re.escape(s) + r"(?!\w)", re.IGNORECASE), s)
    for s in _ALL_SKILLS
]

# Domain → human readable tag
_DOMAIN_DISPLAY: dict[str, str] = {
    "programming": "programming",
    "frontend": "frontend",
    "backend": "backend",
    "cloud_devops": "cloud-devops",
    "database": "database",
    "ai_ml": "ai-ml",
    "data_engineering": "data-engineering",
    "itsm": "itsm",
    "project_management": "project-management",
    "testing": "qa-testing",
    "mobile": "mobile",
    "security": "security",
    "networking_telecom": "networking-telecom",
    "version_control": "version-control",
    "blockchain": "blockchain",
}

# ---------------------------------------------------------------------------
# Layer 1 — Regex extractors
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)

# Indian phone: +91-XXXXX-XXXXX, 9XXXXXXXXX, (0XX) XXXX-XXXX etc.
_PHONE_RE = re.compile(
    r"(?:(?:\+?91[\s\-.]?)?[6-9]\d{9}|"           # Indian mobile
    r"(?:\+\d{1,3}[\s\-.]?)?\(?\d{2,4}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{3,4})",  # International
)

_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-]+)/?",
    re.IGNORECASE,
)

_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([\w\-]+)/?",
    re.IGNORECASE,
)

# Experience stated directly — handles all common phrasings:
#   "8 years' experience"        (apostrophe between years/experience)
#   "12 of years experience"     (inverted "of years" order)
#   "5+ years of experience"     (standard)
#   "10 yrs experience"          (abbreviation)
_EXPLICIT_EXP_RE = re.compile(
    r"(\d+\.?\d*)\s*\+?\s*(?:of\s+)?(?:years?|yrs?)[\s']*(?:of\s+)?(?:experience|exp)",
    re.IGNORECASE,
)

# Fresher / zero-experience detection — checked before any year computation
_FRESHER_RE = re.compile(
    r"\b(fresher|fresh\s+graduate|recent\s+graduate|entry[\s\-]level|"
    r"no\s+experience|0\s+years?\s+(?:of\s+)?experience)\b",
    re.IGNORECASE,
)

# Date ranges for computing experience: Jan 2015 – Present, 2012 – 2020, etc.
# NOTE: This is now only used as a last resort; prefer explicit statements + LLM.
_DATE_RANGE_RE = re.compile(
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s*[\.,]?\s*(\d{4})"
    r"|\b(20\d{2}|19[89]\d)\b",
    re.IGNORECASE,
)

# Education context words — years near these are graduation years, NOT work experience
_EDUCATION_CONTEXT_RE = re.compile(
    r"\b(university|college|school|institute|board|diploma|graduation|"
    r"B\.?E|B\.?Tech|B\.?Sc|MCA|MBA|M\.?Tech|SSC|HSC|CGPA|percentage|"
    r"passing\s+year|passed\s+in|batch)\b",
    re.IGNORECASE,
)

# Education degrees
_DEGREE_RE = re.compile(
    r"\b(B\.?Tech|B\.?E\.?|B\.?Sc|B\.?Com|B\.?A\.?|BCA|"
    r"M\.?Tech|M\.?E\.?|M\.?Sc|M\.?Com|M\.?A\.?|MCA|MBA|"
    r"Ph\.?D\.?|B\.?Pharm|M\.?Pharm|"
    r"Bachelor|Master|Doctorate)\b",
    re.IGNORECASE,
)

# JD-specific: experience range
_EXP_RANGE_RE = re.compile(
    r"(\d+)\s*[-–—to]+\s*(\d+)\s*(?:years?|yrs?)|"
    r"(?:minimum|atleast|at least|min\.?)\s*(\d+)\s*(?:years?|yrs?)|"
    r"(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+)?experience",
    re.IGNORECASE,
)

# Qualification keywords (for JD)
_QUAL_RE = re.compile(
    r"\b(B\.?Tech|B\.?E\.?|Bachelor|Master|M\.?Tech|MCA|MBA|Ph\.?D|"
    r"Graduation|Post[\s\-]?graduation|Any degree|Engineering)\b",
    re.IGNORECASE,
)


def _extract_email(text: str) -> Optional[str]:
    m = _EMAIL_RE.search(text)
    return m.group(0).lower() if m else None


def _extract_phone(text: str) -> Optional[str]:
    for m in _PHONE_RE.finditer(text):
        phone = m.group(0).strip()
        if len(re.sub(r"\D", "", phone)) >= 9:
            return phone
    return None


def _extract_linkedin(text: str) -> Optional[str]:
    m = _LINKEDIN_RE.search(text)
    if m:
        return f"https://linkedin.com/in/{m.group(1)}"
    return None


def _extract_github(text: str) -> Optional[str]:
    m = _GITHUB_RE.search(text)
    if m:
        username = m.group(1)
        # Filter out common false positives
        if username.lower() not in ("actions", "apps", "features", "marketplace"):
            return f"https://github.com/{username}"
    return None


def _extract_experience_years(text: str) -> Optional[float]:
    """
    Extract total years of experience — in priority order:

    1. Fresher detection → 0.0
    2. Explicit self-stated phrases ("8 years' experience", "12 of years experience")
    3. Return None (caller will use LLM result instead)

    The old date-range-span approach is intentionally removed because scanning all
    years in a document (including education years) produces wildly wrong results
    (e.g. "BCA 2004" → 2026-2004 = 22 years for someone with 12 years experience).
    The Groq LLM handles cases where no explicit phrase is found.
    """
    # Priority 1: fresher / zero experience
    if _FRESHER_RE.search(text):
        return 0.0

    # Priority 2: explicit self-stated experience
    exp_matches = _EXPLICIT_EXP_RE.findall(text)
    if exp_matches:
        values = [float(x) for x in exp_matches if x]
        return max(values)

    # Return None → caller will use Groq LLM result
    return None


def _extract_skills(text: str) -> tuple[list[str], list[str]]:
    """
    Return (matched_skills, domain_tags).
    Skills are deduped, preserving canonical capitalisation.
    """
    found: dict[str, str] = {}  # lower → canonical
    for pattern, canonical in _SKILL_PATTERNS:
        if pattern.search(text):
            found[canonical.lower()] = canonical

    skills = sorted(found.values(), key=lambda s: s.lower())

    # Derive domain tags from matched skills
    domains_hit: set[str] = set()
    for lower_skill in found:
        d = _SKILL_DOMAIN.get(lower_skill)
        if d:
            domains_hit.add(_DOMAIN_DISPLAY.get(d, d))

    return skills, sorted(domains_hit)


def _extract_education(text: str) -> list[Education]:
    """
    Regex-based education extraction is intentionally minimal — it only
    serves as a fallback when the LLM is not available.

    Returns at most one entry per unique degree abbreviation, preferring
    the full form when both appear on the same line (e.g. "Bachelor of
    Computer Applications (BCA)" → one entry, not two).
    """
    # Find all degree matches with their positions
    matches: list[tuple[int, str]] = []
    for m in _DEGREE_RE.finditer(text):
        matches.append((m.start(), m.group(0)))

    if not matches:
        return []

    # Deduplicate: if two matches are within 80 chars of each other,
    # keep only the longer one (e.g. "Bachelor" over "BCA" on same line)
    kept: list[tuple[int, str]] = []
    for pos, degree in matches:
        too_close = False
        for kpos, kdegree in kept:
            if abs(pos - kpos) < 80:
                # Keep the longer form
                if len(degree) > len(kdegree):
                    kept.remove((kpos, kdegree))
                else:
                    too_close = True
                break
        if not too_close:
            kept.append((pos, degree))

    results: list[Education] = []
    seen_keys: set[str] = set()

    for pos, degree in kept[:5]:
        key = re.sub(r"[^A-Z]", "", degree.upper())
        if key in seen_keys:
            continue
        seen_keys.add(key)

        snippet = text[pos: pos + 150]
        yr_match = re.search(r"\b(19\d{2}|20\d{2})\b", snippet)
        year = int(yr_match.group(1)) if yr_match else None
        results.append(Education(degree=degree, year=year))

    return results


def _extract_exp_range_jd(text: str) -> Optional[str]:
    """Extract experience range from a JD (e.g. '3-5 years', 'minimum 5 years')."""
    m = _EXP_RANGE_RE.search(text)
    if not m:
        return None
    g = m.groups()
    if g[0] and g[1]:
        return f"{g[0]}-{g[1]} years"
    if g[2]:
        return f"Minimum {g[2]} years"
    if g[3]:
        return f"{g[3]}+ years"
    return None


def _extract_qualification_jd(text: str) -> Optional[str]:
    m = _QUAL_RE.search(text)
    return m.group(0) if m else None


# ---------------------------------------------------------------------------
# Layer 3 — Groq LLM extraction
# ---------------------------------------------------------------------------

_CV_PROMPT = """\
You are a resume parser. Extract information from the resume below and return ONLY a valid JSON object with these exact keys. No markdown, no explanation — raw JSON only.

{{
  "full_name": "candidate's full name or null",
  "current_title": "current or most recent job title or null",
  "location": "city and/or state/country where the candidate lives/works or null",
  "total_experience_years": <number or null>,
  "summary": "2-3 sentence professional summary capturing the candidate's strengths or null",
  "education": [
    {{"degree": "full degree name", "field": "field of study or null", "institution": "university/college name or null", "year": <graduation year or null>}}
  ]
}}

Critical rules:
1. full_name: the person's name only, never a job title or company.
2. current_title: most recent designation. If none found return null.
3. location: city/state where the person lives, not company HQs.
4. total_experience_years:
   - If the CV explicitly states experience (e.g. "8 years experience", "12 of years experience", "5+ years") → use that number exactly.
   - If the person is a FRESHER (fresh/recent graduate, only has academic projects, no paid employment under any company) → return 0.
   - NEVER derive this from education graduation year. Only count paid professional work.
5. education: Return ONE entry per qualification. If the text shows both a full name and abbreviation on the same line (e.g. "Bachelor of Computer Applications (BCA)"), return ONE entry with degree="Bachelor of Computer Applications", NOT two separate entries.
6. Return null for any field you cannot confidently determine.

Resume text:
{text}
"""

_JD_PROMPT = """\
You are a job description parser. Return ONLY a valid JSON object with these keys. No markdown, no explanation — raw JSON only.

{{
  "job_title": "exact job title or null",
  "location": "job location (city/country) or 'Remote' or null",
  "jd_summary": "2-3 sentence summary of the role, key responsibilities, and ideal candidate or null"
}}

Rules:
- Return ONLY the JSON object, no markdown, no explanation.
- Use null for fields you cannot determine.

Job Description:
{text}
"""


def _call_groq(prompt: str) -> Optional[dict]:
    """
    Call Groq LLM with the given prompt. Returns parsed JSON dict or None.
    Uses the fast evaluator model (llama-3.1-8b-instant).
    """
    try:
        import config as app_config
        from groq import Groq

        api_key = getattr(app_config, "GROQ_API_KEY", "")
        if not api_key:
            return None

        model = getattr(app_config, "GROQ_EVALUATOR_MODEL", "llama-3.1-8b-instant")
        client = Groq(api_key=api_key)

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=600,
            timeout=20,
        )

        content = resp.choices[0].message.content or ""
        # Strip markdown code fences if present
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content.strip())

        return json.loads(content)

    except json.JSONDecodeError as exc:
        logger.warning("[structured_extractor] Groq returned non-JSON: %s", exc)
        return None
    except Exception as exc:
        logger.warning("[structured_extractor] Groq call failed: %s", exc)
        return None


def _safe_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() != "null" else None


def _safe_float(val: Any) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_cv(text: str) -> ParsedCV:
    """
    Parse a CV/resume text into structured fields.
    Runs regex pass first, then Groq LLM for missing name/title/location.
    """
    if not text or not text.strip():
        return ParsedCV(confidence=0.0)

    # ── Layer 1: Regex pass ─────────────────────────────────────────────────
    email       = _extract_email(text)
    phone       = _extract_phone(text)
    linkedin    = _extract_linkedin(text)
    github      = _extract_github(text)
    exp_years   = _extract_experience_years(text)
    education   = _extract_education(text)
    skills, domain_tags = _extract_skills(text)

    # ── Layer 3: Groq LLM ────────────────────────────────────────────────────
    llm_data: dict = {}
    prompt = _CV_PROMPT.format(text=text[:3000])
    llm_raw = _call_groq(prompt)

    method = "regex"
    if llm_raw and isinstance(llm_raw, dict):
        llm_data = llm_raw
        method = "regex+groq"

    # Merge: LLM fills gaps that regex can't reliably handle
    full_name    = _safe_str(llm_data.get("full_name"))
    current_title = _safe_str(llm_data.get("current_title"))
    location     = _safe_str(llm_data.get("location"))
    summary      = _safe_str(llm_data.get("summary"))

    # Experience years: regex explicit statement wins; otherwise always use LLM.
    # The LLM reads context properly (e.g. "12 of years experience", freshers)
    # whereas the old date-range fallback picked up education years incorrectly.
    if exp_years is None:
        llm_exp = _safe_float(llm_data.get("total_experience_years"))
        exp_years = llm_exp  # could still be None if LLM returns null

    # Education: LLM result always wins — it returns full degree+field+institution+year
    # in one clean entry, whereas regex produces duplicates (e.g. "Bachelor" + "BCA").
    # Only fall back to regex results if LLM returned nothing at all.
    if isinstance(llm_data.get("education"), list) and llm_data["education"]:
        llm_education: list[Education] = []
        seen_deg: set[str] = set()
        for edu_raw in llm_data["education"][:6]:
            if not isinstance(edu_raw, dict):
                continue
            degree = _safe_str(edu_raw.get("degree"))
            if not degree:
                continue
            # Dedup by first 6 chars of degree (catches minor wording differences)
            key = re.sub(r"\s+", "", degree.lower())[:6]
            if key in seen_deg:
                continue
            seen_deg.add(key)
            raw_year = edu_raw.get("year")
            parsed_year: Optional[int] = None
            try:
                if raw_year is not None:
                    parsed_year = int(float(raw_year))
            except (TypeError, ValueError):
                pass
            llm_education.append(Education(
                degree=degree,
                field=_safe_str(edu_raw.get("field")),
                institution=_safe_str(edu_raw.get("institution")),
                year=parsed_year,
            ))
        if llm_education:
            education = llm_education  # replace regex result entirely

    # Confidence: based on how many key fields we got
    filled = sum(bool(x) for x in [full_name, email, current_title, location, skills])
    confidence = min(0.95, 0.3 + filled * 0.13)

    return ParsedCV(
        full_name=full_name,
        email=email,
        phone=phone,
        linkedin_url=linkedin,
        github_url=github,
        location=location,
        current_title=current_title,
        total_experience_years=exp_years,
        summary=summary,
        skills=skills,
        education=education,
        domain_tags=domain_tags,
        parse_method=method,
        confidence=confidence,
    )


def parse_jd(text: str) -> ParsedJD:
    """
    Parse a Job Description into structured fields.
    """
    if not text or not text.strip():
        return ParsedJD(confidence=0.0)

    # ── Layer 1: Regex pass ─────────────────────────────────────────────────
    exp_range    = _extract_exp_range_jd(text)
    min_qual     = _extract_qualification_jd(text)
    skills, domain_tags = _extract_skills(text)

    # ── Layer 3: Groq LLM ────────────────────────────────────────────────────
    llm_data: dict = {}
    prompt = _JD_PROMPT.format(text=text[:2000])
    llm_raw = _call_groq(prompt)

    method = "regex"
    if llm_raw and isinstance(llm_raw, dict):
        llm_data = llm_raw
        method = "regex+groq"

    job_title  = _safe_str(llm_data.get("job_title"))
    location   = _safe_str(llm_data.get("location"))
    jd_summary = _safe_str(llm_data.get("jd_summary"))

    filled = sum(bool(x) for x in [job_title, location, skills, exp_range])
    confidence = min(0.9, 0.3 + filled * 0.15)

    return ParsedJD(
        job_title=job_title,
        location=location,
        experience_range=exp_range,
        minimum_qualification=min_qual,
        required_skills=skills,
        domain_tags=domain_tags,
        jd_summary=jd_summary,
        parse_method=method,
        confidence=confidence,
    )


def parsed_cv_to_dict(p: ParsedCV) -> dict:
    return {
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "linkedin_url": p.linkedin_url,
        "github_url": p.github_url,
        "location": p.location,
        "current_title": p.current_title,
        "total_experience_years": p.total_experience_years,
        "summary": p.summary,
        "skills": p.skills,
        "education": [
            {
                "degree": e.degree,
                "field": e.field,
                "institution": e.institution,
                "year": e.year,
            }
            for e in p.education
        ],
        "domain_tags": p.domain_tags,
        "parse_method": p.parse_method,
        "confidence": p.confidence,
    }


def parsed_jd_to_dict(p: ParsedJD) -> dict:
    return {
        "job_title": p.job_title,
        "location": p.location,
        "experience_range": p.experience_range,
        "minimum_qualification": p.minimum_qualification,
        "required_skills": p.required_skills,
        "domain_tags": p.domain_tags,
        "jd_summary": p.jd_summary,
        "parse_method": p.parse_method,
        "confidence": p.confidence,
    }
