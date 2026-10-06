"""Refresh the public chapters from local research sources without executing R.

Run locally: python scripts/publish-content.py
Requires Python 3.10+ and Pandoc 3+. GitHub builds use the committed output and
do not need Pandoc, R, the research workspace or its workbooks.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DIAGRAMS = {
    "framework": "framework/book_framework_shared_evaluation_gap",
    "objective": "objective/synthetic_judo_cohort_nextday_prediction",
}
TITLES = {"framework": "Framework", "objective": "Objective"}
MEASURES = [
    "weight_cutting_usuallykg",
    "weight_cutting_daysbefore",
    "weight_regain_nextweekcomp",
    "weight_cutting_maxkg",
    "weight_current",
]


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_objective_svg(contents: bytes) -> bytes:
    """Restore eight missing coordinate separators in the source book icon.

    Its generator joins the control y coordinate to the constant endpoint x=86.
    Match only the confirmed malformed path attributes; leave all other artwork
    and the research source file unchanged.
    """
    for y in (-41, -31, -21, -11, -1, 9, 19, 29):
        original = f'd="M13 {y + 5}Q43 {y - 13}86 {y}"'.encode()
        corrected = f'd="M13 {y + 5}Q43 {y - 13} 86 {y}"'.encode()
        contents = contents.replace(original, corrected)
    return contents


def read_sheet(path: Path, sheet_name: str) -> list[list[str]]:
    """Read stored cell values using the XLSX archive; never open it for writing."""
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            tree = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(item.itertext()) for item in tree.findall("s:si", NS)]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationship = next(
            (sheet.attrib[f"{{{REL}}}id"] for sheet in workbook.findall("s:sheets/s:sheet", NS)
             if sheet.attrib["name"] == sheet_name), None
        )
        if relationship is None:
            raise ValueError(f"Missing sheet {sheet_name!r} in {path.name}")
        links = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(item.attrib["Target"] for item in links if item.attrib["Id"] == relationship)
        location = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        sheet = ET.fromstring(archive.read(location))
        cells = {}
        for cell in sheet.findall("s:sheetData/s:row/s:c", NS):
            reference = cell.attrib["r"]
            match = re.fullmatch(r"([A-Z]+)(\d+)", reference)
            column = 0
            for letter in match.group(1):
                column = column * 26 + ord(letter) - 64
            value = cell.find("s:v", NS)
            if cell.attrib.get("t") == "inlineStr":
                inline = cell.find("s:is", NS)
                text = "".join(inline.itertext()) if inline is not None else ""
            elif value is not None and value.text is not None:
                text = strings[int(value.text)] if cell.attrib.get("t") == "s" else value.text
            else:
                text = ""
            if text != "":
                cells[(int(match.group(2)), column)] = text
        if not cells:
            return []
        first = min(row for row, _ in cells)
        last = max(row for row, _ in cells)
        width = max(column for row, column in cells if row == first)
        return [[cells.get((row, column), "") for column in range(1, width + 1)]
                for row in range(first, last + 1)]


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def escape(value: str) -> str:
        return str(value).replace("|", r"\|").replace("\n", " ")
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(escape(value) for value in row) + " |" for row in rows]
    return "\n".join(lines)


def prepare_markdown(source: str, chapter: str, facts: dict, definitions: list[list[str]]) -> str:
    body = re.sub(r"\A---\r?\n[\s\S]*?\r?\n---\r?\n", "", source)

    def chunk(match: re.Match) -> str:
        options, code = match.group(1), match.group(2).strip()
        if re.search(r"include\s*=\s*FALSE", options, re.I):
            return ""
        if "knitr::include_graphics" in code:
            expected = DIAGRAMS[chapter].split("/")[-1]
            if expected not in code:
                raise ValueError(f"Unregistered figure in {chapter}")
            caption_match = re.search(r'fig\.cap\s*=\s*"((?:\\.|[^"\\])*)"', options)
            caption = caption_match.group(1) if caption_match else ""
            figure = (f'<figure class="chapter-figure"><a href="figures/{chapter}.svg" '
                      f'target="_blank" rel="noopener" aria-label="Open the full {TITLES[chapter]} diagram">'
                      f'<img src="figures/{chapter}.svg" alt="{TITLES[chapter]} study diagram" '
                      'loading="lazy" decoding="async"></a>')
            if caption:
                figure += f"<figcaption>{html.escape(caption)}</figcaption>"
            return "\n" + figure + "</figure>\n"
        result = f'\n<details class="code-block">\n<summary>R code</summary>\n\n```r\n{code}\n```\n\n</details>\n'
        if "definitions <- definitions[" in code:
            result += "\n" + markdown_table(["Variable", "Description", "Unit"], definitions) + "\n"
        return result

    body = re.sub(r"```\{r([^}]*)\}\r?\n([\s\S]*?)```", chunk, body)
    body = body.replace('`r nrow(data)`', str(facts["records"]))
    body = body.replace('`r sum(names(data) != "UID")`', str(facts["studyVariables"]))
    body = re.sub(r"\n# Setup\s*\n(?=# )", "\n", body)
    if re.search(r"(?<!`)`r\s+", body):
        raise ValueError(f"Unresolved inline R expression in {chapter}")
    return body.strip() + "\n"


def render(pandoc: str, markdown: str, bibliography: Path, chapter: str) -> str:
    result = subprocess.run(
        [pandoc, "--from=markdown", "--to=html5", "--citeproc", "--mathml",
         "--bibliography", str(bibliography), "--metadata=link-citations:true",
         f"--id-prefix={chapter}-", "--shift-heading-level-by=1", "--wrap=none"],
        input=markdown, text=True, encoding="utf-8", capture_output=True, check=True,
    )
    if result.stderr.strip():
        raise ValueError(f"Pandoc reported a publication issue:\n{result.stderr.strip()}")
    return result.stdout


def standalone(chapter: str, fragment: str) -> str:
    body = fragment.replace('"figures/', '"../figures/')
    title = TITLES[chapter]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · synSPORT</title><meta name="description" content="The full {title.lower()} chapter of the synSPORT judo research study.">
<link rel="stylesheet" href="../fonts/roboto.css"><link rel="stylesheet" href="chapter.css"></head><body><main>
<nav><a href="../#{chapter}">← Return to the study</a><span>synSPORT</span></nav>
<h1>{title}</h1><article>{body}</article>
<footer><a href="../#{chapter}">Return to the interactive study</a></footer>
</main></body></html>
'''


CHAPTER_CSS = '''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f5f4ef;color:#20312b;font-family:Roboto,system-ui,sans-serif;font-size:17px;line-height:1.75}main{max-width:1050px;margin:auto;padding:30px 30px 70px}nav{display:flex;justify-content:space-between;gap:20px;padding-bottom:22px;border-bottom:1px solid #cad3ca;font-size:14px}a{color:#235f78;text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid #769666;outline-offset:5px}h1{font-size:clamp(44px,7vw,80px);line-height:1.05;letter-spacing:-.045em;margin:55px 0}h2{font-size:30px;line-height:1.2;margin:50px 0 20px}h3{font-size:23px;margin:35px 0 15px}p{margin:18px 0}table{display:block;border-collapse:collapse;width:100%;overflow:auto;font-size:14px;margin:24px 0}th,td{text-align:left;vertical-align:top;padding:12px 15px;border-bottom:1px solid #ccd5cc;min-width:120px}th{background:#e5ebe1}img{display:block;max-width:100%;height:auto;margin:20px auto}.chapter-figure{margin:35px 0}.chapter-figure img{background:white}figcaption{font-size:13px;line-height:1.6;color:#506056}details{border-block:1px solid #d0d8cc;margin:22px 0}summary{cursor:pointer;padding:12px 0;font-size:14px}pre{padding:20px;background:#e8ece4;overflow:auto;font-size:12px;line-height:1.65}code{font-family:Consolas,monospace;font-size:.88em}pre code{font-size:inherit}math[display=block]{display:block;max-width:100%;overflow:auto;padding:14px 0}.csl-entry{margin:18px 0;font-size:15px;overflow-wrap:anywhere}.citation{font-size:.96em}footer{border-top:1px solid #cad3ca;margin-top:45px;padding-top:25px;font-size:14px}@media(max-width:600px){main{padding:20px 20px 50px}body{font-size:16px}h2{font-size:26px}table{font-size:12px}th,td{padding:10px}nav{font-size:12px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "dev")
    parser.add_argument("--pandoc", default=shutil.which("pandoc"))
    arguments = parser.parse_args()
    if not arguments.pandoc:
        raise SystemExit("Pandoc is required for the local publication refresh.")
    source = arguments.source_dir.resolve()
    bibliography = source / "bibliography.bib"
    workbook = source / "data/judo/judo.xlsx"
    dictionary = source / "data/judo/judoDIC.xlsx"
    inputs = [bibliography, workbook, dictionary]
    inputs += [source / f"{chapter}JD.Rmd" for chapter in TITLES]
    inputs += [source / "figures" / f"{name}.{extension}"
               for name in DIAGRAMS.values() for extension in ("svg", "png")]
    hashes = {str(path.relative_to(source)).replace("\\", "/"): checksum(path) for path in inputs}

    records = read_sheet(workbook, "data")
    facts = {"records": len(records) - 1,
             "studyVariables": sum(name != "UID" for name in records[0])}
    reference = read_sheet(dictionary, "dictionary")
    positions = [reference[0].index(name) for name in ("variable", "description", "unit")]
    by_variable = {row[positions[0]]: [row[position] for position in positions] for row in reference[1:]}
    definitions = [by_variable[name] for name in MEASURES]
    del records, reference, by_variable

    chapters = {}
    for chapter, title in TITLES.items():
        raw = (source / f"{chapter}JD.Rmd").read_text(encoding="utf-8-sig")
        prepared = prepare_markdown(raw, chapter, facts, definitions)
        fragment = render(arguments.pandoc, prepared, bibliography, chapter)
        chapters[chapter] = {
            "title": title,
            "html": fragment,
            "source": f"chapters/{chapter}.html",
            "figure": f"figures/{chapter}.svg",
            "figurePng": f"figures/{chapter}.png",
        }

    for path in inputs:
        key = str(path.relative_to(source)).replace("\\", "/")
        if checksum(path) != hashes[key]:
            raise ValueError(f"Source changed during publication: {key}")
    output = {
        "chapters": chapters,
        "meta": {
            "sourceHashes": hashes,
            "questionnaire": facts,
            "renderer": subprocess.check_output([arguments.pandoc, "--version"], text=True).splitlines()[0],
            "rExecuted": False,
        },
    }
    for directory in (ROOT / "content", ROOT / "public/chapters", ROOT / "public/figures"):
        directory.mkdir(parents=True, exist_ok=True)
    for chapter, entry in chapters.items():
        (ROOT / "public/chapters" / f"{chapter}.html").write_text(standalone(chapter, entry["html"]), encoding="utf-8")
        for extension in ("svg", "png"):
            figure_source = source / "figures" / f"{DIAGRAMS[chapter]}.{extension}"
            figure_output = ROOT / "public/figures" / f"{chapter}.{extension}"
            if chapter == "objective" and extension == "svg":
                figure_output.write_bytes(normalize_objective_svg(figure_source.read_bytes()))
            else:
                shutil.copyfile(figure_source, figure_output)
    (ROOT / "public/chapters/chapter.css").write_text(CHAPTER_CSS, encoding="utf-8")
    (ROOT / "content/chapters.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Published two chapters using {facts['records']} reference records and {facts['studyVariables']} study variables. No R code was executed.")


if __name__ == "__main__":
    main()
