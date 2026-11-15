"""List every sentence Teleloadzai can show, for translation and review.

Run from the project folder:  python dev/texts_list.py data/texts.json docs/TEXTS.md
Reads web/index.html (visible text, placeholder / title / aria-label, the
script's string literals) and the Python files (string literals, not
docstrings, not explain.py's evidence nor the words matched in a program's
output). A heuristic: it lists, a person decides."""
import ast, re, sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "teleloadzai"
out = []

def wordy(s: str) -> bool:
    s = s.strip()
    if len(s) < 3 or not re.search(r"[A-Za-z]{2}", s):
        return False
    if re.fullmatch(r"[\w\-./:#%?=&\[\]*+()^$|\\{}<>,;!@~`'\"]+", s) and " " not in s:
        return False                       # ids, selectors, paths, regexes
    if re.match(r"^(https?:|/api/|#|\.|data:|var\(|--)", s):
        return False
    if s.count(" ") == 0 and not s[:1].isupper():
        return False
    if re.search(r"[{};]\s*$|=>|function\b|\$\(|getElementById|querySelector", s):
        return False
    if re.fullmatch(r"[a-z\-]+( [a-z\-]+)*", s) and len(s.split()) <= 3 and not re.search(r"[aeiou]", s):
        return False
    return True

# ---- index.html
html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
lines = html.splitlines()
in_script = in_style = in_comment = in_block = False
for no, line in enumerate(lines, 1):
    # HTML comments over several lines, and JS /* ... */ blocks: never shown.
    if in_comment:
        if "-->" in line:
            in_comment = False
            line = line.split("-->", 1)[1]
        else:
            continue
    if "<!--" in line and "-->" not in line.split("<!--", 1)[1]:
        in_comment = True
        line = line.split("<!--", 1)[0]
    if in_block:
        if "*/" in line:
            in_block = False
            line = line.split("*/", 1)[1]
        else:
            continue
    if in_script and "/*" in line and "*/" not in line.split("/*", 1)[1] and not re.search(r"""["'`][^"'`]*/\*""", line):
        in_block = True
        line = line.split("/*", 1)[0]
    low = line.lower()
    if "<style" in low: in_style = True
    if "<script" in low: in_script = True
    if in_style:
        if "</style>" in low: in_style = False
        continue
    if in_script:
        if "</script>" in low: in_script = False
        code = re.sub(r"//.*$", "", line) if not re.search(r"https?://", line) else line
        if code.strip().startswith(("*", "/*", "//")):
            continue
        for m in re.finditer(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|`((?:[^`\\]|\\.)*)`', code):
            s = next(g for g in m.groups() if g is not None)
            if wordy(s) and (" " in s.strip() or s[:1].isupper()):
                out.append(("index.html", no, "js", s))
        continue
    stripped = re.sub(r"<!--.*?-->", "", line)
    for attr in re.finditer(r'(placeholder|title|aria-label|alt)="([^"]+)"', stripped):
        if wordy(attr.group(2)):
            out.append(("index.html", no, attr.group(1), attr.group(2)))
    for text in re.split(r"<[^>]+>", stripped):
        if wordy(text) and not text.strip().startswith(("<!--", "-->")):
            out.append(("index.html", no, "html", text.strip()))

# ---- Python
for path in sorted(ROOT.glob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant):
                docs.add(id(node.body[0].value))
    # Never shown: explain.py's evidence (seen=) and the words matched in a
    # program's output (words=), regexes, user agents, code run by Python.
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in ("seen", "words"):
            for inner in ast.walk(node.value):
                docs.add(id(inner))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and (
                node.value.startswith(("^", "(?", "Mozilla/", "from ", "import ")) or "\\d" in node.value):
            docs.add(id(node))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            s = node.value
            if wordy(s) and " " in s.strip() and len(s.split()) >= 3 and not s.startswith(("http", "--", "-")):
                out.append((path.name, node.lineno, "py", s))
        if isinstance(node, ast.JoinedStr) and id(node) not in docs:
            s = "".join(v.value if isinstance(v, ast.Constant) else "{…}" for v in node.values)
            if wordy(s) and len(s.split()) >= 3:
                out.append((path.name, node.lineno, "py-f", s))

by_file = {}
for f, *_ in out:
    by_file[f] = by_file.get(f, 0) + 1
print("total candidates:", len(out))
for f, n in sorted(by_file.items(), key=lambda x: -x[1]):
    print(f"  {f}: {n}")
Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")

# The Markdown list for translation: one table per file, f-string pieces
# merged (the whole sentence, with {…} where a value goes), duplicates once.
if len(sys.argv) > 2:
    import time
    whole = [e for e in out if e[2] != "py" or not any(
        f2 == e[0] and l2 == e[1] and k2 == "py-f" for f2, l2, k2, _ in out)]
    lines = ["# Texts shown by Teleloadzai",
             "",
             f"> Made {time.strftime('%Y-%m-%d')} by a script that reads the code (`web/index.html` and the Python files).",
             "> It is the list for translation: every sentence the window, its messages and its errors can show.",
             "> It is made by reading the code, so a line may still be a word nobody sees: check before translating.",
             "> `{…}` or `${…}` marks a value put in by the program (a name, a number).",
             ""]
    seen_text = set()
    for name in sorted({e[0] for e in whole}, key=lambda f: (f != "index.html", f)):
        rows = []
        for f, no, kind, s in whole:
            text = " ".join(s.split()).replace("|", "\\|")
            if f != name or (f, text) in seen_text:
                continue
            seen_text.add((f, text))
            rows.append(f"| {no} | {text} |")
        lines += [f"## `{name}` ({len(rows)})", "", "| Line | Text |", "|---|---|", *rows, ""]
    Path(sys.argv[2]).write_text("\n".join(lines), encoding="utf-8")
    print("written:", sys.argv[2], sum(1 for l in lines if l.startswith("| ") and not l.startswith("| Line")), "rows")
