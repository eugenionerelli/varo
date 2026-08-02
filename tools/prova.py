#!/usr/bin/env python3
"""Check varo before it goes out.

Two things get checked here. That the plugin is shaped the way Claude Code
expects, because a typo in a manifest fails silently and the plugin simply
never loads. And that the hook behaves on real repositories: it has to speak
where there is a site, stay quiet where there is not, and never take a session
down with it.

    python3 tools/prova.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
HOOK = RADICE / "hooks" / "stato.py"

passate = 0
fallite: list[str] = []


def prova(nome: str, condizione: bool, dettaglio: str = "") -> None:
    global passate
    if condizione:
        passate += 1
        print(f"  ok   {nome}")
    else:
        fallite.append(f"{nome}{': ' + dettaglio if dettaglio else ''}")
        print(f"  NO   {nome}{': ' + dettaglio if dettaglio else ''}")


def esegui_hook(cwd: Path | str) -> tuple[str, int]:
    """Run the hook the way Claude Code does, and give back stdout and rc."""
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"cwd": str(cwd)}),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return out.stdout.strip(), out.returncode


def git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)


def sito_finto(base: Path, *, con_config: list[str] = (), pagina: str = "index.html") -> Path:
    """A throwaway repo holding a site, so the checks touch nothing real."""
    d = base
    d.mkdir(parents=True, exist_ok=True)
    (d / pagina).parent.mkdir(parents=True, exist_ok=True)
    (d / pagina).write_text("<!doctype html><title>prova</title>", encoding="utf-8")
    for nome in con_config:
        (d / nome).write_text("", encoding="utf-8")
    git(["init", "-q", "-b", "main"], d)
    git(["config", "user.email", "prova@example.com"], d)
    git(["config", "user.name", "Prova"], d)
    git(["add", "-A"], d)
    git(["commit", "-qm", "primo"], d)
    return d


def main() -> int:
    print("\nManifesto e struttura\n")

    manifesto = RADICE / ".claude-plugin" / "plugin.json"
    prova("il manifesto esiste", manifesto.exists())
    dati = {}
    if manifesto.exists():
        try:
            dati = json.loads(manifesto.read_text(encoding="utf-8"))
            prova("il manifesto è json valido", True)
        except json.JSONDecodeError as e:
            prova("il manifesto è json valido", False, str(e))
    for campo in ("name", "version", "description"):
        prova(f"il manifesto ha {campo}", bool(dati.get(campo)))

    hooks = RADICE / "hooks" / "hooks.json"
    prova("hooks.json esiste", hooks.exists())
    if hooks.exists():
        try:
            h = json.loads(hooks.read_text(encoding="utf-8"))
            prova("hooks.json è json valido", True)
            prova("l'hook si aggancia a SessionStart", "SessionStart" in h.get("hooks", {}))
            testo = hooks.read_text(encoding="utf-8")
            prova(
                "l'hook usa CLAUDE_PLUGIN_ROOT invece di un percorso fisso",
                "${CLAUDE_PLUGIN_ROOT}" in testo,
            )
        except json.JSONDecodeError as e:
            prova("hooks.json è json valido", False, str(e))

    mercato = RADICE / ".claude-plugin" / "marketplace.json"
    prova("marketplace.json esiste", mercato.exists())
    if mercato.exists():
        try:
            m = json.loads(mercato.read_text(encoding="utf-8"))
            prova("marketplace.json è json valido", True)
            nomi = [p.get("name") for p in m.get("plugins", [])]
            prova("il marketplace elenca varo", "varo" in nomi, str(nomi))
        except json.JSONDecodeError as e:
            prova("marketplace.json è json valido", False, str(e))

    prova("la skill c'è", (RADICE / "skills" / "varo" / "SKILL.md").exists())
    prova("l'agente c'è", (RADICE / "agents" / "site-auditor.md").exists())

    for f in (RADICE / "skills" / "varo" / "SKILL.md", RADICE / "agents" / "site-auditor.md"):
        if f.exists():
            testo = f.read_text(encoding="utf-8")
            prova(f"{f.name} ha il frontmatter", testo.startswith("---"))
            prova(f"{f.name} dichiara name e description",
                  "name:" in testo[:400] and "description:" in testo[:400])

    print("\nL'hook su repository veri\n")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        sito = sito_finto(base / "sito", con_config=[".nojekyll"])
        out, rc = esegui_hook(sito)
        prova("esce senza errore su un sito", rc == 0, f"rc={rc}")
        prova("su un sito dice qualcosa", bool(out))
        if out:
            try:
                testo = json.loads(out)["hookSpecificOutput"]["additionalContext"]
                prova("l'uscita ha la forma che Claude Code legge", True)
                prova("riconosce GitHub Pages", "GitHub" in testo)
            except (json.JSONDecodeError, KeyError) as e:
                prova("l'uscita ha la forma che Claude Code legge", False, str(e))

        # Una cartella senza pagine non è un sito: deve tacere, perché quasi
        # tutte le sessioni non parlano di siti e un hook che parla comunque
        # diventa rumore che si impara a saltare.
        muto = base / "muto"
        muto.mkdir()
        (muto / "note.txt").write_text("niente", encoding="utf-8")
        git(["init", "-q"], muto)
        out, rc = esegui_hook(muto)
        prova("tace dove non c'è un sito", out == "" and rc == 0, out[:60])

        # Fuori da git non c'è niente da dire, e non deve rompersi.
        fuori = base / "fuori"
        fuori.mkdir()
        (fuori / "index.html").write_text("<!doctype html>", encoding="utf-8")
        out, rc = esegui_hook(fuori)
        prova("tace fuori da un repository", out == "" and rc == 0)

        # Una cartella che non esiste: capita con sessioni riprese da altrove.
        out, rc = esegui_hook(base / "questa-non-esiste")
        prova("non si rompe su una cartella inesistente", rc == 0, f"rc={rc}")

        # Il caso che ha fatto nascere lo strumento: config di più host insieme.
        molti = sito_finto(base / "molti", con_config=["vercel.json", "netlify.toml"])
        out, _ = esegui_hook(molti)
        prova(
            "segnala config di più host nello stesso repo",
            "more than one host" in out,
        )

        # Un sito tenuto in site/ o docs/: è comunque un sito da mantenere.
        annidato = sito_finto(base / "annidato", pagina="site/index.html")
        out, _ = esegui_hook(annidato)
        prova("trova un sito dentro site/", bool(out))

        # Nessun indirizzo inventato quando l'host non è GitHub Pages: stampare
        # un link che non ha mai funzionato è peggio che non stamparne nessuno.
        cf = sito_finto(base / "cloudflare", con_config=["wrangler.toml"])
        git(["remote", "add", "origin", "https://github.com/tale/quale.git"], cf)
        out, _ = esegui_hook(cf)
        prova("non inventa un indirizzo github.io su Cloudflare",
              "github.io" not in out, out[:80])

    print("\nStile\n")

    stylecheck = RADICE / "tools" / "stylecheck.py"
    if stylecheck.exists():
        pubblici = [
            str(RADICE / "README.md"),
            str(RADICE / "skills" / "varo" / "SKILL.md"),
            str(RADICE / "agents" / "site-auditor.md"),
            str(HOOK),
        ]
        pubblici = [p for p in pubblici if Path(p).exists()]
        out = subprocess.run(
            [sys.executable, str(stylecheck), *pubblici],
            capture_output=True, text=True,
        )
        prova("i testi pubblici passano lo stylecheck", out.returncode == 0,
              (out.stdout + out.stderr).strip()[:400])
    else:
        prova("stylecheck presente", False, "tools/stylecheck.py manca")

    print()
    if fallite:
        print(f"{passate} passate, {len(fallite)} fallite\n")
        for f in fallite:
            print(f"  - {f}")
        return 1
    print(f"{passate} passate, 0 fallite\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
