"""
Reads the prompt file and any accompanying document files.

Everything is treated as plain text (no PDF/DOCX/XLSX parsing). By design,
both the prompt and any "documents" are meant to be exactly what you'd
naturally type into Claude Chat's input box — plain sentences and simple
numbered/bulleted lists, nothing fancier. A plain .txt file captures that
perfectly. Markdown syntax (headers, links, tables) still works fine if
you use it, but it's optional, not required.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


@dataclass
class ParsedInput:
    prompt_text: str
    prompt_path: str
    documents: List["ParsedDocument"] = field(default_factory=list)

    @property
    def document_count(self) -> int:
        return len(self.documents)

    @property
    def combined_text(self) -> str:
        parts = [self.prompt_text]
        parts.extend(doc.text for doc in self.documents)
        return "\n\n".join(parts)


@dataclass
class ParsedDocument:
    path: str
    text: str


def read_text_file(path: str) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def collect_documents(docs_path: str | None) -> List[ParsedDocument]:
    """
    docs_path may be:
      - None                -> no documents
      - a path to one file  -> single document
      - a path to a folder  -> every plain text file inside it (.txt, .md, .markdown)
    """
    if not docs_path:
        return []

    if os.path.isfile(docs_path):
        return [ParsedDocument(path=docs_path, text=read_text_file(docs_path))]

    if os.path.isdir(docs_path):
        docs: List[ParsedDocument] = []
        for name in sorted(os.listdir(docs_path)):
            full = os.path.join(docs_path, name)
            if os.path.isfile(full) and os.path.splitext(name)[1].lower() in TEXT_EXTENSIONS:
                docs.append(ParsedDocument(path=full, text=read_text_file(full)))
        return docs

    raise FileNotFoundError(f"Docs path not found: {docs_path}")


def parse_input(prompt_path: str, docs_path: str | None) -> ParsedInput:
    prompt_text = read_text_file(prompt_path)
    documents = collect_documents(docs_path)
    return ParsedInput(prompt_text=prompt_text, prompt_path=prompt_path, documents=documents)
