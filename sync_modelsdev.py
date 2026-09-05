#!/usr/bin/env python3
"""
sync_modelsdev.py — models.dev-Abgleich fuer das AI Provider Registry.

models.dev (https://models.dev/api.json) liefert den groessten offenen
Katalog aus Anbietern und Modellen (213 Provider / ~7500 Modelle). Dieses
Repo wird dagegen von Hand gepflegt. Das Skript hilft, ohne die Webseite
zu oeffnen:

    python3 sync_modelsdev.py fetch          # Mirror nach catalog/models-dev ziehen
    python3 sync_modelsdev.py report         # Luecken melden (nur lesen)
    python3 sync_modelsdev.py enrich ZAI     # fehlende Modelle fuer _einen_ Provider
                                             # als YAML-Entwurf anzeigen (dry-run)
    python3 sync_modelsdev.py enrich --all --write
                                             # alle Provider erweitern (Dateien schreiben)

Prinzip: Die YAML-Dateien sind die Wahrheit. `enrich` ERGAENZT nur Modelle,
die noch nicht in einer providers/*.yaml stehen, und fasst vorhandene
Eintraege nie an. Ohne `--write` wird nichts geschrieben.

Neue PROVIDER (ohne vorhandene providers/<id>.yaml) legt `report` nur als
Vorschlag vor; Anlegen erfolgt manuell nach dem Runbook in docs/maintenance.md
(providers/*.yaml + registry.json + llms.txt + index.html, dann
python3 validate_registry.py -v).
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml fehlt:  pip install pyyaml --break-system-packages")

ROOT = Path(__file__).resolve().parent
MIRROR = ROOT / "catalog" / "models-dev" / "api.json"
MODELS_JSON = ROOT / "catalog" / "models-dev" / "models.json"
META = ROOT / "catalog" / "models-dev" / "meta.json"
URL = "https://models.dev/api.json"
URL_MODELS = "https://models.dev/models.json"

# models.dev-Schreibweisen, die im Repo anders heissen.
PROVIDER_ALIASES = {
    "togetherai": "together",
    "moonshotai": "kimi",
    "novita-ai": "novita",
    "fireworks-ai": "fireworks",
    "llmgateway-providers": "llmgateway",
    "stepfun-ai-step-plan": "stepfun-ai",
    "stepfun-step-plan": "stepfun",
    "tipresias": "brandl",
}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
def fetch() -> None:
    import datetime
    import urllib.request

    MIRROR.parent.mkdir(parents=True, exist_ok=True)
    parts: list[tuple[Path, str]] = [(MIRROR, URL), (MODELS_JSON, URL_MODELS)]
    blob: dict[str, bytes] = {}
    for target, url in parts:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-provider-registry/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            blob[target.name] = r.read()
        raw = blob[target.name]
        if target == MIRROR and json.loads(raw) and not isinstance(json.loads(raw), dict):
            sys.exit("Achtung: api.json hat unerwartete Struktur, Abbruch.")
        target.write_bytes(raw)

    provs = json.loads(blob["api.json"])
    meta = {
        "fetched_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "source": URL,
        "api_bytes": len(blob["api.json"]),
        "api_sha256": hashlib.sha256(blob["api.json"]).hexdigest(),
        "models_json_bytes": len(blob["models.json"]),
        "providers": len(provs),
        "models": sum(len(p.get("models", {})) for p in provs.values()),
        "providers_with_api": sum(1 for p in provs.values() if p.get("api")),
    }
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Mirror aktualisiert: {meta['providers']} Provider, "
          f"{meta['models']} Modelle (api.json {meta['api_bytes']//1024} KiB, "
          f"models.json {meta['models_json_bytes']//1024} KiB).")


# ---------------------------------------------------------------------------
# gemeinsame Lade-Funktionen
# ---------------------------------------------------------------------------
def load_mirror() -> dict:
    if not MIRROR.exists():
        sys.exit(f"Kein Mirror unter {MIRROR}. Erst `python3 sync_modelsdev.py fetch`.")
    return json.loads(MIRROR.read_text("utf-8"))


def repo_provider_stems() -> set[str]:
    return {p.stem for p in (ROOT / "providers").glob("*.yaml")}


def resolve_mirror_name(mid: str, repo: set[str]) -> str | None:
    n = norm(mid)
    for cand in repo:
        if norm(cand) == n:
            return cand
    if mid in PROVIDER_ALIASES and PROVIDER_ALIASES[mid] in repo:
        return PROVIDER_ALIASES[mid]
    return None


def load_repo_provider(stem: str) -> dict:
    p = ROOT / "providers" / f"{stem}.yaml"
    return yaml.safe_load(p.read_text("utf-8")) or {}


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def report() -> None:
    mirror = load_mirror()
    repo = repo_provider_stems()

    missing, mapped = [], {}
    for mid in sorted(mirror):
        hit = resolve_mirror_name(mid, repo)
        if hit:
            mapped[mid] = hit
        else:
            missing.append(mid)

    print(f"== Mirror: {len(mirror)} Provider, {sum(len(p['models']) for p in mirror.values())} Modelle ==\n")

    print(f"--- Provider nur im Mirror (kein providers/*.yaml): {len(missing)} ---")
    for mid in missing:
        n = len(mirror[mid].get("models", {}))
        api = mirror[mid].get("api") or "-"
        print(f"  {mid:<26} {n:>4} Modelle   api={api}")

    both = {k: v for k, v in mapped.items()}
    lone = sorted(r for r in repo if r not in set(both.values()))
    print(f"\n--- Repo-Provider ohne Mirror-Zwilling: {len(lone)} ---")
    print("  " + ", ".join(lone))

    print("\n--- Endpoint-Luecken (Repo hat kein endpoint, Mirror hat api) ---")
    gaps = []
    for mid, hit in both.items():
        api = mirror[mid].get("api")
        if not api:
            continue
        y = load_repo_provider(hit)
        if not y.get("endpoint") and not y.get("api_spec"):
            gaps.append((hit, api))
    if not gaps:
        print("  keine")
    for hit, api in sorted(gaps):
        print(f"  {hit:<26} -> {api}")

    print("\n--- Modell-Luecken (Anzahl je Provider: Mirror vs. Repo) ---")
    for mid, hit in sorted(both.items(), key=lambda kv: kv[1]):
        y = load_repo_provider(hit)
        repo_n = len(y.get("models", []))
        mir_n = len(mirror[mid].get("models", {}))
        if mir_n > repo_n:
            print(f"  {hit:<26} Mirror {mir_n:>4}  /  Repo {repo_n:<4}  (+{mir_n-repo_n})")


# ---------------------------------------------------------------------------
# enrich
# ---------------------------------------------------------------------------
def tag_from_model(m: dict) -> list[str]:
    tags: list[str] = []
    if m.get("reasoning"):
        tags.append("reasoning")
    if m.get("tool_call"):
        tags.append("tools")
    if m.get("structured_output"):
        tags.append("json_mode")
    if m.get("open_weights"):
        tags.append("open_weights")
    mod_in = (m.get("modalities") or {}).get("input") or []
    if "image" in mod_in:
        tags.append("vision")
    if "audio" in mod_in:
        tags.append("audio")
    if m.get("attachment"):
        tags.append("multimodal")
    if m.get("status") == "beta":
        tags.append("beta")
    return tags


def model_entry(m: dict, style: str) -> dict:
    slug = m["id"].split("/", 1)[1] if "/" in m["id"] else m["id"]
    e: dict = {"id": slug}
    lim = m.get("limit") or {}
    if style == "A":
        if m.get("name"):
            e["name"] = m["name"]
        if m.get("description"):
            e["description"] = m["description"]
        if lim.get("context"):
            e["context_window"] = int(lim["context"])
        if lim.get("output"):
            e["output_limit"] = int(lim["output"])
        if m.get("release_date"):
            e["release_date"] = m["release_date"]
    if m.get("family"):
        e["family"] = m["family"]
    if style == "B" and lim.get("context"):
        e["context_window"] = int(lim["context"])
    cost = m.get("cost") or {}
    pricing = {}
    for src, dst in (("input", "input"), ("output", "output"),
                     ("cache_read", "cached_read"), ("cache_write", "cached_write")):
        if cost.get(src) is not None:
            pricing[dst] = float(cost[src])
    if pricing:
        e["pricing"] = pricing
    if m.get("status") == "deprecated":
        e["deprecated"] = True
    if m.get("status") == "beta":
        e["beta"] = True
    tags = tag_from_model(m)
    if tags:
        e["tags"] = tags
    return e


def fmt_model(e: dict, style: str) -> str:
    """Ein Modell-Eintrag im Stil der YAML-Dateien. Stil A: '- id:' auf
    Spalte 0 (generierte Dateien, 'tags' als Blockliste). Stil B: '  - id:'
    (kuratierte Dateien, 'tags' als Flow-Liste). Mutiert das Dict nicht."""
    e = dict(e)
    tags = e.pop("tags", None)
    body = yaml.safe_dump(e, sort_keys=False, allow_unicode=True).splitlines()
    if style == "A":
        out = ["- " + body[0]] + ["  " + line for line in body[1:]]
        if tags:
            out.append("  tags:")
            out += ["  - " + t for t in tags]
    else:
        out = ["  - " + body[0]] + ["    " + line for line in body[1:]]
        if tags:
            out.append("    tags: [" + ", ".join(tags) + "]")
    return "\n".join(out)


def _detect_style(stem: str) -> str:
    """Stil der providers-Datei ermitteln: 'A' (Modelle auf Spalte 0,
    generierte Dateien) oder 'B' (2er-Indent, kuratierte Dateien)."""
    p = ROOT / "providers" / f"{stem}.yaml"
    try:
        lines = p.read_text("utf-8").splitlines()
    except OSError:
        return "B"
    idx = next((i for i, l in enumerate(lines)
                if re.match(r"^models:\s*$", l)), None)
    if idx is None:
        return "B"
    for l in lines[idx + 1:]:
        m = re.match(r"^(\s*)-\s", l)
        if m:
            return "A" if len(m.group(1)) == 0 else "B"
    return "B"


def enrich(provider: str | None, write: bool, limit: int) -> None:
    mirror = load_mirror()
    repo = repo_provider_stems()

    # repo-Stem -> Mirror-ID (nur Matches; Alias-Mapping inklusive)
    matched = {hit: mid for mid in sorted(mirror)
               if (hit := resolve_mirror_name(mid, repo))}

    if provider and provider.upper() != "ALL":
        want = provider.strip()
        hits = {s: m for s, m in matched.items()
                if s.upper() == want.upper() or m.upper() == want.upper()}
        if not hits:
            sys.exit(f"Provider '{provider}' im Mirror nicht gefunden.")
    else:
        hits = matched

    todo = 0
    errors: list[str] = []
    for stem, mid in sorted(hits.items()):
        y = load_repo_provider(stem)
        style = _detect_style(stem)
        existing = set()
        for m in y.get("models", []):
            if isinstance(m, dict):
                existing.add(m.get("id"))
            elif isinstance(m, str):
                existing.add(m)
        fresh = [model_entry(m, style) for m in mirror[mid].get("models", {}).values()
                 if (m["id"].split("/", 1)[1] if "/" in m["id"] else m["id"]) not in existing]
        if not fresh:
            continue
        fresh = fresh[:limit]
        todo += len(fresh)
        print(f"## {stem}  (aus '{mid}', {len(fresh)} neue Eintraege, Stil {style})")
        if not write:
            print("\n".join(fmt_model(m, style) for m in fresh))
            continue
        if (err := _append_models(stem, fresh, style)):
            errors.append(f"{stem}: {err}")

    print(f"\n== {todo} neue Modell-Eintraege {'geschrieben' if write else 'als Entwurf (dry-run)'} ==")
    if errors:
        print("Uebersprungen (manuell ergaenzen):")
        for e in errors:
            print("  -", e)
    print("Tipp: nach '--write' unbedingt  python3 validate_registry.py -v  laufen lassen.")


def _append_models(stem: str, fresh: list[dict], style: str) -> str | None:
    """Fuegt neue Eintraege in die 'models:'-Sektion ein (vor dem naechsten
    Top-Level-Key bzw. am Dateiende). Handgeschriebene Inhalte inkl.
    Kommentare bleiben unangetastet. Rueckgabe: Fehlermeldung oder None."""
    p = ROOT / "providers" / f"{stem}.yaml"
    text = p.read_text("utf-8")
    lines = text.splitlines()

    idx = next((i for i, l in enumerate(lines)
                if re.match(r"^models:\s*$", l)), None)
    if idx is None:
        return "keine 'models:'-Sektion gefunden"

    # Einschubpunkt: Zeilenindex des naechsten Top-Level-Keys nach 'models:'
    ins = None
    for i in range(idx + 1, len(lines)):
        l = lines[i]
        if l.strip() and not l.startswith((" ", "-", "\t")):
            ins = i
            break

    block = "\n".join(fmt_model(m, style) for m in fresh)
    if ins is None:
        text = text.rstrip("\n") + "\n" + block + "\n"
    else:
        new_lines = lines[:ins] + block.splitlines()
        if not new_lines[-1] or new_lines[-1].strip() == "":
            pass
        else:
            new_lines.append("")
        new_lines += lines[ins:]
        text = "\n".join(new_lines).rstrip("\n") + "\n"
    p.write_text(text, encoding="utf-8")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="models.dev-Abgleich fuer das Registry")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="Mirror (api.json) nach catalog/models-dev ziehen")

    sub.add_parser("report", help="Luecken zwischen Mirror und Repo anzeigen")

    p = sub.add_parser("enrich", help="fehlende Modelle eines Providers ergaenzen")
    p.add_argument("provider", nargs="?", default=None,
                   help="Provider-ID (Repo-Stem) oder 'ALL'; ohne Angabe: dry-run fuer alle")
    p.add_argument("--write", action="store_true", help="wirklich in die YAML-Dateien schreiben")
    p.add_argument("--limit", type=int, default=5000, help="max. neue Eintraege je Provider")

    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch()
    elif args.cmd == "report":
        report()
    elif args.cmd == "enrich":
        enrich(args.provider or "ALL", args.write, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())