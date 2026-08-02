#!/usr/bin/env python3
"""Read the state of a static site and hand it to the session as context.

This runs on every SessionStart, so it has one hard rule: no network, ever.
The facts worth having at the start of a session are all local (which host
this deploys to, whether local is ahead of the remote, what is uncommitted),
and they cost a few milliseconds. Checking whether the live site actually
answers costs a second or more, and a second on every session start is a
second nobody asked for. That check belongs to `varo audit`, which is run on
purpose.

Silence is the normal outcome. Most sessions are not about a website, and a
hook that prints something anyway is noise that people learn to skip.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# How long any single git call gets. A repo on a slow or unmounted disk should
# make the hook give up, not hang the session it was meant to speed up.
TIMEOUT = 2.0

# A config file that belongs to one host says where this site was meant to go.
# Finding several of them is a finding in itself: a repo forked from a template
# carries the old host's config, the new host ignores it, and the redirects and
# security headers written there never take effect anywhere.
SEGNI = [
    ("wrangler.toml", "Cloudflare"),
    ("wrangler.jsonc", "Cloudflare"),
    ("wrangler.json", "Cloudflare"),
    ("netlify.toml", "Netlify"),
    ("vercel.json", "Vercel"),
    (".nojekyll", "GitHub Pages"),
    ("_config.yml", "GitHub Pages"),
]

# Shared by Cloudflare and Netlify, so on their own they name no single host.
SEGNI_CONDIVISI = ["_headers", "_redirects", "public/_headers", "public/_redirects"]

# Branches a host deploys from when nobody has said otherwise.
RAMI_PRODUZIONE = ["main", "master", "gh-pages", "production"]

# Something that answers on the web. Without one of these there is no site here.
# `site/` and `docs/` are in the list because a project whose main job is
# something else often keeps its page there, and that page is still a site
# somebody has to keep working.
PROVE_SITO = [
    "index.html",
    "public/index.html",
    "src/index.html",
    "dist/index.html",
    "site/index.html",
    "docs/index.html",
    "www/index.html",
]


def git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def radice(cwd: Path) -> Path | None:
    top = git(["rev-parse", "--show-toplevel"], cwd)
    return Path(top) if top else None


def e_un_sito(root: Path) -> bool:
    return any((root / p).exists() for p in PROVE_SITO)


def host(root: Path) -> tuple[str | None, list[str]]:
    """The host this deploys to, and every host config lying around.

    Returned separately on purpose. One config means a clear answer. Several
    mean the repo is carrying settings for hosts it does not deploy to, and
    somebody should be told rather than have a host silently picked for them.
    """
    trovati = [(n, e) for n, e in SEGNI if (root / n).exists()]
    condivisi = [n for n in SEGNI_CONDIVISI if (root / n).exists()]
    nomi = [n for n, _ in trovati] + condivisi

    if trovati:
        etichette = sorted({e for _, e in trovati})
        return (etichette[0] if len(etichette) == 1 else " / ".join(etichette)), nomi
    if condivisi:
        return "Cloudflare or Netlify", nomi

    origin = git(["remote", "get-url", "origin"], root) or ""
    if "github.com" in origin:
        return "GitHub (Pages, if it is turned on)", nomi
    return None, nomi


def indirizzo(root: Path, etichetta: str | None) -> str | None:
    """The public address, only when it can be worked out rather than guessed.

    A custom domain is written down, so it is trustworthy. A github.io address
    follows from the remote, so it holds only when GitHub is the host. Guessing
    one for a site that lives on Cloudflare prints a link that has never worked,
    which is worse than printing nothing.
    """
    for nome in ("CNAME", "public/CNAME"):
        dominio = root / nome
        if not dominio.exists():
            continue
        try:
            righe = dominio.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            continue
        if righe and righe[0].strip():
            return f"https://{righe[0].strip()}"

    if not etichetta or "GitHub" not in etichetta:
        return None
    origin = git(["remote", "get-url", "origin"], root) or ""
    if "github.com" not in origin:
        return None
    pezzo = origin.split("github.com", 1)[1].lstrip(":/")
    if pezzo.endswith(".git"):
        pezzo = pezzo[:-4]
    if "/" not in pezzo:
        return None
    utente, repo = pezzo.split("/", 1)
    if repo == f"{utente}.github.io":
        return f"https://{utente}.github.io/"
    return f"https://{utente}.github.io/{repo}/"


def ramo_produzione(root: Path) -> str | None:
    """The branch the host deploys, which is rarely the one you are sitting on."""
    testa = git(["symbolic-ref", "refs/remotes/origin/HEAD"], root)
    if testa and "/" in testa:
        return testa.rsplit("/", 1)[-1]
    for nome in RAMI_PRODUZIONE:
        if git(["rev-parse", "--verify", f"refs/remotes/origin/{nome}"], root):
            return nome
    return None


def non_spinti(root: Path) -> int:
    """Commits that exist only on this machine."""
    upstream = git(["rev-parse", "--abbrev-ref", "@{upstream}"], root)
    if not upstream:
        return 0
    n = git(["rev-list", "--count", f"{upstream}..HEAD"], root)
    return int(n) if n and n.isdigit() else 0


def non_pubblicati(root: Path, ramo: str) -> int:
    """Commits pushed to some branch, and missing from the one that deploys.

    This is the one that hides best. The work is committed, pushed, and safe,
    so every local check is green, and none of it is on the site.
    """
    n = git(["rev-list", "--count", f"origin/{ramo}..HEAD"], root)
    return int(n) if n and n.isdigit() else 0


def riga_stato(root: Path) -> list[str]:
    righe = []
    etichetta, config = host(root)
    if etichetta:
        righe.append(f"- Host: {etichetta}")
    if len(config) > 1:
        righe.append(
            f"- **Config for more than one host in the same repo: {', '.join(config)}.** "
            "Only the host you actually deploy to reads its own file. Redirects "
            "and security headers written in the others do nothing."
        )

    url = indirizzo(root, etichetta)
    if url:
        righe.append(f"- Public address: {url}")

    ramo = ramo_produzione(root)
    corrente = git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if ramo and corrente:
        if corrente != ramo:
            mancanti = non_pubblicati(root, ramo)
            if mancanti:
                righe.append(
                    f"- **On branch `{corrente}`, {mancanti} commit(s) ahead of "
                    f"`{ramo}`.** The site deploys from `{ramo}`, so none of that "
                    "work is live."
                )
            else:
                righe.append(f"- On branch `{corrente}`, deploys come from `{ramo}`.")

    locali = non_spinti(root)
    if locali:
        righe.append(f"- {locali} commit(s) not pushed anywhere yet.")

    sporco = git(["status", "--porcelain"], root)
    if sporco:
        n = len([r for r in sporco.splitlines() if r.strip()])
        righe.append(f"- {n} uncommitted file(s).")

    ultimo = git(["log", "-1", "--format=%h %s (%cr)"], root)
    if ultimo:
        righe.append(f"- Last commit: {ultimo}")
    return righe


def main() -> int:
    try:
        dati = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        dati = {}
    cwd = Path(dati.get("cwd") or os.getcwd())

    root = radice(cwd)
    if not root or not e_un_sito(root):
        return 0

    righe = riga_stato(root)
    if not righe:
        return 0

    testo = "\n".join(
        [
            f"## Static site in this folder ({root.name})",
            "",
            *righe,
            "",
            "Read locally, without touching the network. To find out what the "
            "live site actually does, run the `varo` skill: the repo and "
            "production drift apart quietly, and only one of them is what "
            "people see.",
        ]
    )
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": testo,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # A hook that fails takes the session down with it. Nothing this file
        # reports is worth that, so any surprise ends as silence.
        sys.exit(0)
