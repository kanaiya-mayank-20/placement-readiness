"""End-to-end API tests: admin JD pipeline -> student analysis -> matches -> score -> readiness."""

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.db.models import User
from app.main import app
from app.workers.runner import runner

JD_TEXT = """Backend Engineer - Payments
Acme Pay, Bangalore, hybrid, 2+ years

Responsibilities:
- Design and build REST APIs for payment processing in Python
- Own PostgreSQL schemas, queries and migrations
- Containerise services with Docker and deploy to AWS
- Write tests and keep CI pipelines green

Requirements:
- Strong knowledge of Python and REST API development
- Must have production experience with PostgreSQL and Docker
- Experience with Redis caching is required
- Good to have: Kafka, Kubernetes, AWS
- Bachelor's degree in Computer Science or related field
"""

RESUME_LINES = [
    "Riya Sharma",
    "Backend Developer | Python | FastAPI | PostgreSQL",
    "Experience: 2.5 years at Finlytic (2023-06 to Present)",
    "Built REST APIs with Python, FastAPI, PostgreSQL and Docker",
    "Reduced API latency by 35% with Redis caching",
    "Projects: Payment Gateway API - Python, FastAPI, PostgreSQL, Docker, tests",
    "Skills: Python, FastAPI, PostgreSQL, Docker, Redis, Git, AWS",
    "Education: B.Tech Computer Science, 2022",
    "github.com/riya-dev",
]


def make_pdf(lines: list[str]) -> bytes:
    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = "BT /F1 11 Tf 40 750 Td 16 TL\n"
    content += "\n".join(f"({esc(line)}) Tj T*" for line in lines)
    content += "\nET"

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _login(client: TestClient, email: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_admin() -> str:
    db = SessionLocal()
    try:
        email = "admin@example.com"
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, name="Admin", role="admin")
            db.add(user)
        user.hashed_password = hash_password("adminpass1")  # override any .env-seeded admin
        user.role = "admin"
        db.commit()
        return email
    finally:
        db.close()


def test_health(client: TestClient):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_and_login(client: TestClient):
    resp = client.post(
        "/api/auth/register",
        json={"name": "Student", "email": "student@example.com", "password": "secret123"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["role"] == "student"
    headers = _login(client, "student@example.com", "secret123")
    me = client.get("/api/auth/roles", headers=headers)
    assert me.status_code == 200
    assert "backend" in me.json()["roles"]


def test_admin_upload_jd_and_pipeline(client: TestClient):
    admin_email = _make_admin()
    headers = _login(client, admin_email, "adminpass1")

    resp = client.post(
        "/api/admin/jds",
        json={"company_name": "Acme Pay", "title": "Backend Engineer", "raw_text": JD_TEXT,
              "location": "Bangalore"},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    jd_id = resp.json()["jd_id"]

    assert runner.drain(timeout=120), "jd pipeline did not finish"

    detail = client.get(f"/api/admin/jds/{jd_id}", headers=headers).json()
    assert detail["status"] == "ready", detail.get("error")
    assert detail["role_family"] == "backend"
    assert "python" in detail["must_have"]
    assert "postgresql" in detail["must_have"]
    assert detail["structured"]["summary_text"]

    companies = client.get("/api/admin/companies", headers=headers).json()
    assert companies["total"] >= 1
    acme = next(c for c in companies["items"] if c["name"] == "Acme Pay")
    assert acme["ready_jd_count"] >= 1
    assert "backend" in acme["roles"]


JD_FULL_TEXT = """Internship - AI Engineer (6 months)
DeepSignal AI, Pune, hybrid

About Us
DeepSignal AI builds computer vision products for semiconductor factories in India.

Duration
6 months internship with possible full-time conversion upon successful completion.

Internship Stipend
A minimum monthly stipend of 10,000/- will be provided during the internship phase.

Eligibility
Final year BE/B.Tech (CS, IT, ECE), MCA. GPA above 6.0 required.

Selection Process
1 Aptitude Test
2 MCQ Programming Test
3 HR Interview

Perks
Mentorship from senior engineers, learning budget and medical insurance.

Requirements:
- Strong knowledge of Python and Deep Learning
- Good to have: PyTorch, OpenCV
"""


def test_admin_parse_jd_pdf(client: TestClient):
    """PDF parse endpoint must detect company/JD details without saving anything."""
    admin_email = _make_admin()
    headers = _login(client, admin_email, "adminpass1")
    resp = client.post(
        "/api/admin/jds/parse",
        headers=headers,
        files={"file": ("intern_jd.pdf", make_pdf(JD_FULL_TEXT.splitlines()), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["saved"] is False
    assert "raw_text" in data and len(data["raw_text"]) > 30
    struct = data["structured"]
    assert struct["employment_type"] == "internship"
    assert "10,000" in struct["compensation"]
    assert "b.tech" in struct["eligibility"].lower()
    assert any("aptitude" in r.lower() for r in struct["selection_process"])
    assert len(struct["selection_process"]) >= 2
    assert "6 months" in struct["duration"].lower()
    assert "hybrid" in struct["work_mode"].lower()
    assert "deepsignal" in struct["about"].lower()


def test_admin_jd_overrides_persist(client: TestClient):
    """Admin-provided company detail fields must win over extraction."""
    admin_email = _make_admin()
    headers = _login(client, admin_email, "adminpass1")
    resp = client.post(
        "/api/admin/jds",
        json={
            "company_name": "DeepSignal AI",
            "title": "AI Engineer Intern",
            "raw_text": JD_FULL_TEXT,
            "location": "Pune",
            "industry": "Semiconductors",
            "employment_type": "internship",
            "compensation": "stipend of 12,000/- per month (corrected)",
            "eligibility": "BE/B.Tech (CS, IT, ECE) or MCA, GPA 6.0+",
            "selection_process": ["Aptitude Test", "Coding Test", "Technical Interview"],
            "perks": ["Mentorship", "Medical insurance"],
            "about": "Builds computer vision for semiconductor factories.",
        },
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    jd_id = resp.json()["jd_id"]
    assert runner.drain(timeout=120), "jd pipeline did not finish"

    detail = client.get(f"/api/admin/jds/{jd_id}", headers=headers).json()
    assert detail["status"] == "ready", detail.get("error")
    assert detail["employment_type"] == "internship"
    assert detail["compensation"] == "stipend of 12,000/- per month (corrected)"
    assert detail["eligibility"] == "BE/B.Tech (CS, IT, ECE) or MCA, GPA 6.0+"
    assert detail["selection_process"] == ["Aptitude Test", "Coding Test", "Technical Interview"]
    assert detail["about"] == "Builds computer vision for semiconductor factories."
    assert detail["must_have"], "skills still extracted"
    assert detail["structured"]["parser"]


def test_student_full_flow(client: TestClient):
    headers = _login(client, "student@example.com", "secret123")
    pdf = make_pdf(RESUME_LINES)
    resp = client.post(
        "/api/analyses",
        data={"role": "backend", "github_url": ""},
        files={"resume": ("resume.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    analysis_id = resp.json()["analysis_id"]

    assert runner.drain(timeout=180), "analysis pipeline did not finish"

    status = client.get(f"/api/analyses/{analysis_id}", headers=headers).json()
    assert status["status"] == "done", status.get("error")
    assert status["progress"]["resume"] == "done"

    matches = client.get(f"/api/analyses/{analysis_id}/matches", headers=headers).json()
    assert matches["total_scored"] >= 1
    assert len(matches["items"]) <= 3  # TOP_N_COMPANIES=3 in tests
    first = matches["items"][0]
    assert first["rank"] == 1
    assert 0 <= first["resume_score"] <= 100
    assert 0 <= first["overall_score"] <= 100
    assert first["github_score"] is None  # no github provided
    assert first["company"]
    assert isinstance(first["strengths"], list)

    jd_id = first["jd_id"]
    detail = client.get(f"/api/analyses/{analysis_id}/matches/{jd_id}", headers=headers).json()
    assert detail["breakdown"]["skill_match"]["matched"]
    assert detail["resume_score"] >= 0

    score = client.post(
        f"/api/analyses/{analysis_id}/score", json={"jd_id": jd_id}, headers=headers
    ).json()
    assert score["rank"] >= 1
    assert score["total_companies_scored"] >= 1
    assert "python" in score["matched_skills"]

    readiness = client.post(
        f"/api/analyses/{analysis_id}/readiness", json={"jd_id": jd_id}, headers=headers
    ).json()
    assert readiness["strengths"], readiness
    assert readiness["suggestions_to_improve"], readiness
    assert len(readiness["next_steps"]) >= 3
    assert readiness["gaps"]
    assert "overall_score" not in readiness
    assert "internal_score" not in readiness
    assert readiness["next_steps"][0]["actions"]

    invalid_company = client.post(
        "/api/analyses",
        data={"role": "backend", "github_url": "", "company_id": 999999},
        files={"resume": ("resume.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert invalid_company.status_code == 404

    unavailable_role = client.post(
        "/api/analyses",
        data={"role": "frontend", "github_url": "", "company_id": first["company_id"]},
        files={"resume": ("resume.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert unavailable_role.status_code == 400

    targeted = client.post(
        "/api/analyses",
        data={"role": "backend", "github_url": "", "company_id": first["company_id"]},
        files={"resume": ("resume.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert targeted.status_code == 202, targeted.text
    targeted_id = targeted.json()["analysis_id"]
    assert runner.drain(timeout=180), "targeted analysis pipeline did not finish"
    targeted_matches = client.get(
        f"/api/analyses/{targeted_id}/matches", headers=headers
    ).json()
    assert targeted_matches["items"]
    assert {item["company_id"] for item in targeted_matches["items"]} == {first["company_id"]}


def test_readiness_has_no_scores_anywhere(client: TestClient):
    headers = _login(client, "student@example.com", "secret123")
    analyses = client.get("/api/analyses", headers=headers).json()["items"]
    assert analyses
    analysis_id = analyses[0]["id"]
    matches = client.get(f"/api/analyses/{analysis_id}/matches", headers=headers).json()
    jd_id = matches["items"][0]["jd_id"]
    readiness = client.post(
        f"/api/analyses/{analysis_id}/readiness", json={"jd_id": jd_id}, headers=headers
    ).json()
    blob = str(readiness).lower()
    assert "overall_score" not in blob
    assert "resume_score" not in blob


def test_student_cannot_use_admin_api(client: TestClient):
    headers = _login(client, "student@example.com", "secret123")
    resp = client.get("/api/admin/stats", headers=headers)
    assert resp.status_code == 403


def test_unauthenticated_rejected(client: TestClient):
    assert client.get("/api/analyses").status_code == 401
    assert client.get("/api/companies").status_code == 401
