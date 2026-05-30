from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from agentstack.infra.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedDocument:
    text: str
    source_type: str
    metadata: dict = field(default_factory=dict)


def parse_document(source_type: str, source_uri: str) -> ParsedDocument:
    if source_type == "pdf":
        return _parse_pdf(source_uri)
    if source_type == "markdown":
        return _parse_text(source_uri, source_type="markdown")
    if source_type == "text":
        return _parse_text(source_uri, source_type="text")
    if source_type == "url":
        return _parse_url(source_uri)
    raise ValueError(f"Unsupported source_type: {source_type}")


def _parse_pdf(path: str) -> ParsedDocument:
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as e:
            logger.warning("pdf page extract failed", page=i, error=str(e))
            pages.append("")
    text = "\n\n".join(pages).strip()
    metadata = {
        "page_count": len(reader.pages),
        "filename": Path(path).name,
    }
    return ParsedDocument(text=text, source_type="pdf", metadata=metadata)


def _parse_text(path: str, source_type: str) -> ParsedDocument:
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return ParsedDocument(
        text=text.strip(),
        source_type=source_type,
        metadata={"filename": Path(path).name},
    )


def _parse_url(url: str) -> ParsedDocument:
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        resp = client.get(url, headers={"User-Agent": "agentstack/0.1"})
        resp.raise_for_status()
        html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = "\n".join(line.strip() for line in soup.get_text().splitlines() if line.strip())
    title = soup.title.string.strip() if soup.title and soup.title.string else url
    return ParsedDocument(
        text=text,
        source_type="url",
        metadata={"url": url, "title": title},
    )
