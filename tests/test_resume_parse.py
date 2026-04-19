"""Tests for resume_parse.py."""
from __future__ import annotations

import httpx
import respx
from resume_parse import parse_resume, parse_resume_bytes


def test_parse_resume_bytes_extracts_sections(sample_resume_pdf):
    result = parse_resume_bytes(sample_resume_pdf.read_bytes())
    assert "Harvey Zheng" in result["raw_text"]
    assert "Experience" in result["sections"]
    assert "Education" in result["sections"]
    assert "Skills" in result["sections"]


def test_parse_resume_local_path(sample_resume_pdf):
    result = parse_resume(str(sample_resume_pdf))
    assert "Harvey Zheng" in result["raw_text"]


@respx.mock
def test_parse_resume_remote_url(sample_resume_pdf):
    url = "https://example.com/resume.pdf"
    respx.get(url).mock(return_value=httpx.Response(200, content=sample_resume_pdf.read_bytes()))
    result = parse_resume(url)
    assert "Harvey Zheng" in result["raw_text"]
