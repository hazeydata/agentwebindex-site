"""Reader for the vendored page copy (content/copy.md) and chart alt text (content/chart-alt.md).

All static page text is taken from copy.md at build time, so it is verbatim by construction. Strings that carry
numbers are computed in render.py from latest.json and checked against copy.md by tests (test_dist.py).
"""
import html, re
from pathlib import Path

CONTENT = Path(__file__).resolve().parent / "content"


class Doc:
    def __init__(self, text):
        self.secs = []   # (title, [lines]) for each "## " section; "### " subsections stay inside as lines
        for line in text.splitlines():
            if line.startswith("## "):
                self.secs.append((line[3:].strip(), []))
            elif self.secs:
                self.secs[-1][1].append(line)

    def lines(self, prefix, sub=None):
        """Lines of the section whose heading starts with `prefix` (and, if given, its '### ' subsection `sub`)."""
        hits = [ls for t, ls in self.secs if t.startswith(prefix)]
        if len(hits) != 1:
            raise KeyError(f"copy.md: expected one section starting {prefix!r}, found {len(hits)}")
        ls = hits[0]
        if sub is None:
            return ls
        out, on = [], False
        for l in ls:
            if l.startswith("### "):
                on = l[4:].strip().startswith(sub)
            elif on:
                out.append(l)
        if not out:
            raise KeyError(f"copy.md: no subsection {sub!r} in {prefix!r}")
        return out

    def blocks(self, prefix, sub=None):
        """[(kind, text)] with kind p (paragraph/field line), li (bullet) or h3 ('### ' heading) for a section."""
        out = []
        for l in self.lines(prefix, sub):
            s = l.strip()
            if not s:
                continue
            if s.startswith("### "):
                out.append(("h3", s[4:].strip()))
            elif s.startswith("- "):
                out.append(("li", s[2:].strip()))
            else:
                out.append(("p", s))
        return out

    def field(self, prefix, label, sub=None):
        """Body of the '**Label:** body' / '**Label (human label):** body' line in a section."""
        pat = re.compile(r"^\*\*" + re.escape(label) + r"(?: \(([^)]*)\))?:\*\*\s*(.*)$")
        for kind, t in self.blocks(prefix, sub):
            m = pat.match(t)
            if m:
                return m.group(2).strip()
        raise KeyError(f"copy.md: no field {label!r} in {prefix!r}")

    def field_label(self, prefix, label):
        """Human label in parentheses of a '**ID (Human label):**' field, e.g. DISC-SPON -> Current and past sponsors."""
        pat = re.compile(r"^\*\*" + re.escape(label) + r" \(([^)]*)\):\*\*")
        for _, t in self.blocks(prefix):
            m = pat.match(t)
            if m:
                return m.group(1)
        raise KeyError(label)

    def para(self, prefix, startswith, sub=None):
        for kind, t in self.blocks(prefix, sub):
            if kind == "p" and t.startswith(startswith):
                return t
        raise KeyError(f"copy.md: no paragraph starting {startswith!r} in {prefix!r}")


def load(path=None):
    return Doc(Path(path or CONTENT / "copy.md").read_text())


def alt_texts(path=None):
    """{'pass-rate': alt, 'cost-per-success': alt} from content/chart-alt.md ('- her-<name>-*: "alt"' lines)."""
    out = {}
    for m in re.finditer(r'^- her-([a-z-]+?)-\*: "(.*)"\s*$', Path(path or CONTENT / "chart-alt.md").read_text(), re.M):
        out[m.group(1)] = m.group(2)
    return out


def inline(s):
    """Markdown inline -> HTML: **bold**, [text](url), bare fred@hazeydata.ai as a mailto link. Text is otherwise unchanged."""
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"(?<![\w>/:])(fred@hazeydata\.ai)", r'<a href="mailto:\1">\1</a>', s)
    return s
