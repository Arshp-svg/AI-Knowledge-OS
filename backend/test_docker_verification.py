import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import os
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def test_docker_and_orchestration():
    print("=" * 65)
    print("🐳 TESTING DAY 9: MULTI-STAGE DOCKER & COMPOSE ORCHESTRATION")
    print("=" * 65)

    # 1. Validate Docker Compose Syntax via CLI
    print("\n[1/5] Validating docker-compose.yml configuration...")
    compose_path = BASE_DIR / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml does not exist"
    
    result = subprocess.run(
        ["docker", "compose", "config", "--services"],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=True
    )
    services = [s.strip() for s in result.stdout.strip().splitlines() if s.strip()]
    print(f"  Detected orchestrated services: {services}")
    assert "qdrant" in services, "Missing qdrant service"
    assert "backend" in services, "Missing backend service"
    assert "frontend" in services, "Missing frontend service"
    print("  [PASS] docker-compose.yml syntax and service topology verified.")

    # 2. Inspect Backend Dockerfile
    print("\n[2/5] Inspecting backend multi-stage Dockerfile...")
    backend_dockerfile = BASE_DIR / "backend" / "Dockerfile"
    assert backend_dockerfile.exists(), "backend/Dockerfile does not exist"
    backend_content = backend_dockerfile.read_text(encoding="utf-8")

    assert "FROM python:3.12-slim AS builder" in backend_content, "Missing builder stage in backend Dockerfile"
    assert "FROM python:3.12-slim AS runner" in backend_content, "Missing runner stage in backend Dockerfile"
    assert "useradd" in backend_content and "appuser" in backend_content, "Missing unprivileged appuser in backend Dockerfile"
    assert "USER appuser" in backend_content, "Backend container does not run as non-root user"
    assert "SentenceTransformer" in backend_content, "Missing pre-warmed embeddings model caching"
    assert "flashrank" in backend_content, "Missing pre-warmed FlashRank model caching"
    assert "HEALTHCHECK" in backend_content, "Missing HEALTHCHECK instruction in backend Dockerfile"
    print("  [PASS] Backend Dockerfile enforces multi-stage caching, model pre-warming, and non-root security.")

    # 3. Inspect Frontend Dockerfile
    print("\n[3/5] Inspecting frontend multi-stage Dockerfile & standalone config...")
    frontend_dockerfile = BASE_DIR / "frontend" / "Dockerfile"
    assert frontend_dockerfile.exists(), "frontend/Dockerfile does not exist"
    frontend_content = frontend_dockerfile.read_text(encoding="utf-8")

    assert "FROM node:20-alpine AS deps" in frontend_content, "Missing deps stage in frontend Dockerfile"
    assert "FROM node:20-alpine AS builder" in frontend_content, "Missing builder stage in frontend Dockerfile"
    assert "FROM node:20-alpine AS runner" in frontend_content, "Missing runner stage in frontend Dockerfile"
    assert "USER nextjs" in frontend_content, "Frontend container does not run as non-root user"
    assert ".next/standalone" in frontend_content, "Missing standalone bundle copy in frontend Dockerfile"

    next_config = (BASE_DIR / "frontend" / "next.config.ts").read_text(encoding="utf-8")
    assert 'output: "standalone"' in next_config, "Missing output: 'standalone' in next.config.ts"
    print("  [PASS] Frontend Dockerfile enforces multi-stage standalone build and non-root security.")

    # 4. Deep Health Check Verification
    print("\n[4/5] Testing deep dependency health check endpoint (GET /health)...")
    req = urllib.request.Request("http://127.0.0.1:8000/health")
    with urllib.request.urlopen(req) as resp:
        status_code = resp.status
        health_data = json.loads(resp.read().decode())
        print(f"  HTTP Status: {status_code}")
        print(f"  Service:     {health_data.get('service')} (v{health_data.get('version')})")
        print(f"  Uptime:      {health_data.get('uptime_seconds')}s")
        print(f"  Dependencies:")
        for dep_name, dep_info in health_data.get("dependencies", {}).items():
            print(f"    • {dep_name}: status={dep_info.get('status')} {dep_info}")

        assert status_code == 200, f"Expected 200, got {status_code}"
        assert health_data.get("status") == "healthy", "System status is not healthy"
        assert health_data["dependencies"]["document_store"]["status"] == "healthy"
        assert health_data["dependencies"]["vector_store"]["status"] == "healthy"
        assert health_data["dependencies"]["llm"]["status"] == "configured"
        print("  [PASS] Deep health check verified document store, vector store, and LLM connectivity.")

    # 5. Environment & Volume Isolation Verification
    print("\n[5/5] Validating volume isolation & environment mapping...")
    dockerignore_backend = (BASE_DIR / "backend" / ".dockerignore").read_text(encoding="utf-8")
    assert ".venv" in dockerignore_backend, "backend/.dockerignore should exclude .venv"
    assert "storage/*.db" in dockerignore_backend, "backend/.dockerignore should exclude local db files"

    dockerignore_frontend = (BASE_DIR / "frontend" / ".dockerignore").read_text(encoding="utf-8")
    assert "node_modules" in dockerignore_frontend, "frontend/.dockerignore should exclude node_modules"
    assert ".next" in dockerignore_frontend, "frontend/.dockerignore should exclude .next"
    print("  [PASS] Production build contexts are protected from bloated host artifacts.")

    print("\n" + "=" * 65)
    print("✅ ALL DAY 9 DOCKER & COMPOSE ORCHESTRATION TESTS PASSED!")
    print("=" * 65)

if __name__ == "__main__":
    try:
        test_docker_and_orchestration()
    except Exception as exc:
        print(f"\n❌ Day 9 verification failed: {exc}")
        sys.exit(1)
