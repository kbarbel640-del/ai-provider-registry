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
META = ROOT / "catalog" / "models-dev" / "meta.json"
URL = "https://models.dev/api.json"

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
    import urllib.request

    MIRROR.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "ai-provider-registry/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    provs = json.loads(raw)
    if not isinstance(provs, dict):
        sys.exit("Achtung: api.json hat unerwartete Struktur, Abbruch.")

    MIRROR.write_bytes(raw)
    meta = {
        "fetched_at": __import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc).isoformat(),
        "source": URL,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "providers": len(provs),
        "models": sum(len(p.get("models", {})) for p in provs.values()),
        "providers_with_api": sum(1 for p in provs.values() if p.get("api")),
    }
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Mirror aktualisiert: {meta['providers']} Provider, "
          f"{meta['models']} Modelle ({len(raw)//1024} KiB).")


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
    return tags


def model_entry(m: dict) -> dict:
    e: dict = {"id": m["id"].split("/", 1)[1] if "/" in m["id"] else m["id"]}
    if m.get("family"):
        e["family"] = m["family"]
    lim = m.get("limit") or {}
    if lim.get("context"):
        e["context_window"] = int(lim["context"])
    cost = m.get("cost") or {}
    pricing = {}
    for src, dst in (("input", "input"), ("output", "output"),
                     ("cache_read", "cached_read"), ("cache_write", "cached_write")):
        if cost.get(src) is not None:
            pricing[dst] = float(cost[src])
    if pricing:
        e["pricing"] = pricing
    tags = tag_from_model(m)
    if tags:
        e["tags"] = tags
    return e


def fmt_model(e: dict) -> str:
    """Ein Modell-Eintrag im Stil der kuratierten YAMLs (2er-Einrueckung,
    'tags' als Flow-Liste am Ende). Mutiert das uebergebene Dict nicht."""
    e = dict(e)
    tags = e.pop("tags", None)
    body = yaml.safe_dump(e, sort_keys=False, allow_unicode=True).splitlines()
    out = ["  - " + body[0]] + ["    " + line for line in body[1:]]
    if tags:
        out.append("    tags: [" + ", ".join(tags) + "]")
    return "\n".join(out)


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
    for stem, mid in sorted(hits.items()):
        y = load_repo_provider(stem)
        existing = {m.get("id") for m in y.get("models", []) if isinstance(m, dict)}
        fresh = [model_entry(m) for m in mirror[mid].get("models", {}).values()
                 if (m["id"].split("/", 1)[1] if "/" in m["id"] else m["id"]) not in existing]
        if not fresh:
            continue
        fresh = fresh[:limit]
        todo += len(fresh)
        print(f"## {stem}  (aus '{mid}', {len(fresh)} neue Eintraege)")
        if not write:
            print("\n".join(fmt_model(m) for m in fresh))
            continue
        _append_models(stem, fresh)

    print(f"\n== {todo} neue Modell-Eintraege {'geschrieben' if write else 'als Entwurf (dry-run)'} ==\n"
          "Tipp: nach '--write' unbedingt  python3 validate_registry.py -v  laufen lassen.")


def _append_models(stem: str, fresh: list[dict]) -> None:
    """Haengt neue Eintraege ans Ende von 'models:' an und laesst die
    handgeschriebenen Dateien (inkl. Kommentare) unangetastet."""
    p = ROOT / "providers" / f"{stem}.yaml"
    lines = p.read_text("utf-8").splitlines()

    idx = next((i for i, l in enumerate(lines)
                if re.match(r"^models:\s*$", l)), None)
    if idx is None:
        sys.exit(f"{stem}.yaml: keine 'models:'-Sektion gefunden, bitte manuell ergaenzen.")
    after = lines[idx + 1:]
    if any(re.match(r"^[A-Za-z_][\w-]*:\s*$", l) for l in after):
        sys.exit(f"{stem}.yaml: 'models:' ist nicht die letzte Sektion, bitte manuell ergaenzen.")

    block = "\n".join(fmt_model(m) for m in fresh)
    text = p.read_text("utf-8")
    text = text.rstrip("\n") + "\n" + block + "\n"
    p.write_text(text, encoding="utf-8")


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