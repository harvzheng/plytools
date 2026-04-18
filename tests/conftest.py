"""Shared pytest config. Adds scripts/ to sys.path so tests can import scripts as modules."""
import pathlib
import sys

SCRIPTS_DIR = pathlib.Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pytest
from reportlab.pdfgen import canvas


@pytest.fixture
def sample_resume_pdf(tmp_path):
    """Generate a minimal resume PDF for tests."""
    path = tmp_path / "resume.pdf"
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 12)
    y = 750
    for line in [
        "Harvey Zheng",
        "",
        "Experience",
        "Designer at Example Co (2022-2024)",
        "",
        "Education",
        "UPenn M&TSI (2018)",
        "",
        "Skills",
        "Design, Engineering, Tools",
    ]:
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return path
