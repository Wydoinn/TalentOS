from __future__ import annotations

from app.models.enums import CandidateSource
from app.utils.resume_parser import parse_resume_text
from app.utils.text import extract_required_skills
from app.utils.text import extract_skills


def test_parse_resume_text_prefers_person_name_and_cleans_header_fields() -> None:
    text = """
    MACHINE LEARNING ENGINEER
    Sathish Kumar V
    📍 Tamil Nadu, India
    📞 +91-9567812345
    📧 raghavendran1097@gmail.com
    🔗 linkedin.com/in/sathish-v | github.com/sathish-v
    PROFESSIONAL SUMMARY
    Machine Learning Engineer with 4 years experience building and deploying ML models. Skilled in NLP, recommendation systems, and model deployment.
    TECHNICAL SKILLS
    • Python, TensorFlow, Scikit-learn
    • NLP, Deep Learning
    • FastAPI (deployment)
    • SQL
    PROJECTS
    Recommendation System
    • Built ML-based recommendation model
    • Deployed using FastAPI
    Fraud Detection Model
    • Built classification model
    • Improved prediction accuracy
    EDUCATION
    B.Tech in Computer Science
    PSG College of Technology
    Year: 2022
    """.strip()

    parsed = parse_resume_text(text, source=CandidateSource.external)

    assert parsed.name == "Sathish Kumar V"
    assert parsed.current_title == "Machine Learning Engineer"
    assert parsed.location == "Tamil Nadu, India"
    assert parsed.links["linkedin"] == "https://linkedin.com/in/sathish-v"
    assert parsed.links["github"] == "https://github.com/sathish-v"
    assert parsed.total_experience_years == 4.0
    assert parsed.experience == []
    assert parsed.education[0].institution == "PSG College of Technology"
    assert parsed.education[0].degree == "B.Tech"
    assert [project.name for project in parsed.projects] == [
        "Recommendation System",
        "Fraud Detection Model",
    ]
    assert "fastapi" in parsed.projects[0].technologies
    assert "rag" not in parsed.skills
    assert "git" not in parsed.skills
    assert "Tamil Nadu, India" in parsed.summary
    assert parsed.parsing_quality_score >= 0.7
    assert "📍" not in parsed.summary


def test_extract_skills_avoids_false_matches_inside_words_and_urls() -> None:
    skills = extract_skills(
        "Raghavendran1097@gmail.com github.com/sathish-v Built FastAPI services with SQL and TensorFlow."
    )

    assert "fastapi" in skills
    assert "sql" in skills
    assert "tensorflow" in skills
    assert "rag" not in skills
    assert "git" not in skills


def test_extract_required_skills_does_not_double_count_postgresql_as_sql() -> None:
    skills = extract_required_skills(
        "Build ATS services using FastAPI, PostgreSQL, Pinecone, and Neo4j."
    )

    assert "fastapi" in skills
    assert "postgresql" in skills
    assert "pinecone" in skills
    assert "neo4j" in skills
    assert "sql" not in skills


def test_parse_resume_text_extracts_inline_experience_and_project_stack() -> None:
    text = """
    JOHN DOE
    Senior Backend Engineer
    EXPERIENCE
    Senior Backend Engineer | Example Corp | Jan 2021 - Present
    Built FastAPI and PostgreSQL services for internal tooling.

    Backend Developer | ACME Labs | 2018 - 2020
    Worked on Kafka-based microservices and Python APIs.

    PROJECTS
    Hiring Platform
    Tech Stack: FastAPI, PostgreSQL, Kafka
    Built resume search and recruiter workflow automation.
    """.strip()

    parsed = parse_resume_text(text, source=CandidateSource.internal)

    assert parsed.experience[0].title == "Senior Backend Engineer"
    assert parsed.experience[0].company == "Example Corp"
    assert parsed.experience[0].start_date == "Jan 2021"
    assert parsed.experience[0].end_date == "Present"
    assert {"fastapi", "kafka", "postgresql"}.issubset(set(parsed.projects[0].technologies))
    assert parsed.parsing_quality_score >= 0.75


def test_parse_resume_text_does_not_promote_experience_description_to_company() -> None:
    text = """
    JANE DOE
    Senior Platform Engineer
    EXPERIENCE
    Senior Platform Engineer | Jan 2021 - Present
    Designed and maintained CI/CD pipelines across backend services.
    """.strip()

    parsed = parse_resume_text(text, source=CandidateSource.internal)

    assert parsed.experience[0].title == "Senior Platform Engineer"
    assert parsed.experience[0].company is None
    assert parsed.experience[0].summary == "Designed and maintained CI/CD pipelines across backend services."
