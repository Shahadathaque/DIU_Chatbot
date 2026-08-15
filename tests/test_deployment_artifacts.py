"""Static checks for the lightweight backend deployment artifact."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deploy_requirements_exclude_local_models_and_pipeline_packages() -> None:
    requirements = (ROOT / "requirements-deploy.txt").read_text(encoding="utf-8").lower()

    assert "fastapi==" in requirements
    assert "uvicorn[standard]==" in requirements
    assert "psycopg[binary,pool]==" in requirements
    for forbidden in (
        "torch==",
        "transformers==",
        "sentence-transformers==",
        "playwright==",
        "pdfplumber==",
        "pypdf==",
        "datasets==",
        "peft==",
        "trl==",
    ):
        assert forbidden not in requirements


def test_dockerfile_uses_deploy_requirements_and_provider_port() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "requirements-deploy.txt" in dockerfile
    assert "uvicorn backend.main:app" in dockerfile
    assert "--host 0.0.0.0" in dockerfile
    assert "${PORT:-8000}" in dockerfile
    assert "COPY data" not in dockerfile


def test_render_blueprint_requires_database_and_hosted_runtime_settings() -> None:
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "healthCheckPath: /api/live" in blueprint
    assert "RUNTIME_CATALOG_BACKEND" in blueprint
    assert "value: database" in blueprint
    assert "GENERATOR_BACKEND" in blueprint
    assert "EMBEDDING_BACKEND" in blueprint
    assert "diu_knowledge_chunks_hosted" in blueprint
    assert "sync: false" in blueprint
