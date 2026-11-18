#!/usr/bin/env python3
# Dextend | Developed by Overev | https://overev.com/
"""Render English user guides and their .pl.md translations. Requires Markdown and WeasyPrint."""
import html
from pathlib import Path

import markdown
from weasyprint import HTML

docs = Path(__file__).resolve().parents[1] / "docs"
style = """
@page {
    size: A4; margin: 18mm;
    @bottom-left { content: "Dextend · Overev.com"; font: bold 10pt sans-serif; }
    @bottom-right { content: counter(page) " / " counter(pages); font: 10pt sans-serif; }
}
body { font: 11pt/1.48 sans-serif; color: #232323; }
header { color: #555; font-weight: bold; }
h1 { font-size: 22pt; } h2 { font-size: 15pt; } h3 { font-size: 12pt; }
h1,h2,h3 { break-after: avoid; } li { margin-bottom: .35em; break-inside: avoid; }
code { overflow-wrap: anywhere; } h2 { border-top: 1px solid #ddd; padding-top: .5em; }
"""
for name in ("installation", "operation", "diagnostics"):
    for language, suffix in (("en", ""), ("pl", ".pl")):
        source = (docs / f"{name}{suffix}.md").read_text()
        title = html.escape(source.splitlines()[0].removeprefix("# "))
        body = markdown.markdown(source)
        if name == "installation":
            heading = "Install and check the result" if language == "en" else "Zainstaluj dodatek i sprawdź wynik"
            body = body.replace(f"<h2>{heading}", f'<h2 style="break-before:page">{heading}')
        if name == "operation":
            heading = "Set priorities and Wi-Fi" if language == "en" else "Ustaw priorytet i sieć"
            body = body.replace(f"<h2>{heading}", f'<h2 style="break-before:page">{heading}')
        document = (f'<!doctype html><html lang="{language}"><meta charset="utf-8"><meta name="author" content="Overev">'
                    f'<title>{title}</title><style>{style}</style>'
                    f'<header>Dextend · CPC200-CCPA / A15W</header>{body}</html>')
        HTML(string=document).write_pdf(docs / f"{name}-{language}.pdf")
