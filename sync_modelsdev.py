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
    python3 sync_modelsdev.py generate       # fehlende Provider anlegen (dry-run)
    python3 sync_modelsdev.py generate --write
                                             # Provider anlegen (4 Dateien je Provider:
                                             # providers/*.yaml + registry.json +
                                             # llms.txt + index.html)

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


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------
# Reihenfolge der Supports-Liste in den Repo-Dateien (kanonisch).
CANONICAL_SUPPORTS = ["chat", "vision", "image", "audio", "video", "tools",
                      "json_mode", "streaming", "reasoning", "embeddings",
                      "web_search", "file_extraction", "speech", "moderation",
                      "rerank", "search"]


def api_style_from_npm(npm: str | None) -> str:
    n = (npm or "").lower()
    for kw, style in (("anthropic", "anthropic"), ("google", "google"),
                      ("cohere", "cohere"), ("bedrock", "bedrock"),
                      ("azure", "azure")):
        if kw in n:
            return style
    return "openai"


def supports_from_mirror(mp: dict) -> list[str]:
    s: set[str] = {"chat", "streaming"}
    for mm in mp.get("models", {}).values():
        if mm.get("tool_call"):
            s.add("tools")
        if mm.get("structured_output"):
            s.add("json_mode")
        if mm.get("reasoning"):
            s.add("reasoning")
        mod = mm.get("modalities") or {}
        if "image" in (mod.get("input") or []):
            s.add("vision")
        if "audio" in (mod.get("input") or []):
            s.add("audio")
        if "image" in (mod.get("output") or []):
            s.add("image")
        slug = mm["id"].split("/", 1)[1] if "/" in mm["id"] else mm["id"]
        if "embedding" in slug.lower() or "embedding" in (mm.get("name") or "").lower():
            s.add("embeddings")
    return [c for c in CANONICAL_SUPPORTS if c in s]


def mirror_has_free_model(mp: dict) -> bool:
    for mm in mp.get("models", {}).values():
        if mm.get("status") == "deprecated":
            continue
        cost = mm.get("cost") or {}
        if cost.get("input") == 0 and cost.get("output") == 0:
            return True
    return False


def env_var_for(mid: str, mp: dict) -> str:
    env = mp.get("env") or []
    if env and env[0]:
        return env[0]
    return mid.upper().replace("-", "_") + "_API_KEY"


def build_provider_file(mid: str, mp: dict) -> str:
    """Neue providers/<mid>.yaml im kuratierten Stil B aus den Mirror-Daten."""
    style = api_style_from_npm(mp.get("npm"))
    free = mirror_has_free_model(mp)
    doc = mp.get("doc") or ""
    doc_url = doc if doc.startswith("https://") else None
    supports = supports_from_mirror(mp)
    models = list(mp.get("models", {}).values())

    L = [f"name: {mp['name']}"]
    L.append(f"api_style: {style}")
    L.append("auth:")
    L.append("  type: bearer")
    L.append("  header: Authorization")
    L.append('  prefix: "Bearer "')
    L.append(f"  env_var: {env_var_for(mid, mp)}")
    if doc_url:
        L.append(f"  doc_url: {doc_url}")
    L.append("pricing:")
    L.append(f"  free: {str(free).lower()}")
    L.append("  pay_as_you_go: true")
    if doc_url:
        L.append(f"  doc_url: {doc_url}")
    L.append("  free_basis: "
             + ("hat $0-Modelle in models.dev" if free
                else "kein $0-Modell in models.dev"))
    L.append("supports:")
    L += [f"  - {c}" for c in supports]
    L.append(f"endpoint: {mp['api']}")
    L.append("notes:")
    L.append("  source: generiert aus https://models.dev/api.json")
    L.append(f"  model_catalog_size: {len(models)}")
    L.append("  kuratiert: auth/pricing/supports aus Mirror-Feldern abgeleitet")
    L.append("models:")
    L += [fmt_model(model_entry(m, "B"), "B") for m in models]
    return "\n".join(L) + "\n"


def registry_entry(mid: str, mp: dict) -> dict:
    return {
        "id": mid,
        "free": mirror_has_free_model(mp),
        "api_style": api_style_from_npm(mp.get("npm")),
        "supports": supports_from_mirror(mp),
        "endpoint": mp.get("api"),
        "model_count": len(mp.get("models", {})),
    }


def generate(write: bool) -> None:
    mirror = load_mirror()
    repo = repo_provider_stems()

    missing = [mid for mid in sorted(mirror)
               if not resolve_mirror_name(mid, repo)]
    junk = [mid for mid in missing
            if not (mirror[mid].get("api") or "").startswith("https://")]
    todo = [mid for mid in missing if mid not in junk]

    if write:
        entries = [registry_entry(mid, mirror[mid]) for mid in todo]
        # providers/*.yaml schreiben
        for mid in todo:
            (ROOT / "providers" / f"{mid}.yaml").write_text(
                build_provider_file(mid, mirror[mid]), encoding="utf-8")
        # registry.json: Eintraege ans Ende des providers-Arrays
        reg_path = ROOT / "registry.json"
        reg = json.loads(reg_path.read_text("utf-8"))
        reg["providers"] += entries
        import datetime
        reg["metadata"]["last_updated"] = datetime.date.today().isoformat()
        reg_path.write_text(json.dumps(reg, ensure_ascii=False,
                                       indent=2) + "\n", encoding="utf-8")
        # llms.txt: Eintraege ans Ende der Providers-Sektion
        llms_path = ROOT / "llms.txt"
        text = llms_path.read_text("utf-8")
        lines = text.splitlines()
        idx = next((i for i, l in enumerate(lines)
                    if l.strip().startswith("## Providers")), 0)
        end = next((i for i in range(idx + 1, len(lines))
                    if not lines[i].strip()), len(lines))
        add = [f"providers/{mid}.yaml" for mid in todo]
        lines[end:end] = add
        llms_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
        # index.html: <li>-Zeilen vor </ul> der Provider-Liste + Stat hochzaehlen
        html_path = ROOT / "index.html"
        html = html_path.read_text("utf-8")
        items = [f'    <li><a href="providers/{mid}.yaml">{mid}.yaml</a> '
                 f'<span class="badge">free tier: '
                 f'{"yes" if registry_entry(mid, mirror[mid])["free"] else "no"}'
                 f'</span></li>' for mid in todo]
        mark = "  </ul>\n\n  <h2>Models</h2>"
        if mark not in html:
            sys.exit("generate: index.html-Struktur geaendert, Abbruch.")
        html = html.replace(mark, "\n".join(items) + "\n" + mark)
        html = re.sub(
            r'(stat-value">\s*)(\d+)(\s*</div>\s*<div class="stat-label">Providers)',
            lambda m: f"{m.group(1)}{len(repo) + len(todo)}{m.group(3)}",
            html)
        html_path.write_text(html, encoding="utf-8")

        print(f"== {len(todo)} Provider angelegt "
              f"(providers/*.yaml, registry.json, llms.txt, index.html) ==")
        print(f"   Providers gesamt: {len(repo)} -> {len(repo) + len(todo)}")
    else:
        print(f"== {len(todo)} neue Provider wuerden angelegt (dry-run) ==\n")
        for mid in todo:
            mp = mirror[mid]
            print(f"  {mid:<24} {len(mp['models']):>4} Modelle  free="
                  f"{str(mirror_has_free_model(mp)).lower():<5}  "
                  f"{mp['api']}")

    if junk:
        print(f"\nUebersprungen ({len(junk)}, kein HTTPS-Endpoint):")
        for mid in junk:
            print(f"  {mid:<24} api={mirror[mid].get('api') or '-'}")
    print("Tipp: nach '--write' unbedingt  python3 validate_registry.py -v "
          "laufen lassen.")


# ---------------------------------------------------------------------------
# families (models/<family>.yaml aus models.json anreichern)
# ---------------------------------------------------------------------------
def load_models_index() -> dict[str, dict]:
    """models.json nach name und id-Slug indexieren (klein geschrieben)."""
    mj = json.loads(MODELS_JSON.read_text("utf-8"))
    idx: dict[str, dict] = {}
    for k, e in mj.items():
        for key in (e.get("name"), k.split("/", 1)[1]):
            if key:
                idx.setdefault(str(key).lower(), e)
    return idx


def variant_entry(v: dict, src: dict) -> dict:
    """Varianten-Eintrag fuer models/<family>.yaml: name/provider bleiben
    (name = Repo-Modell-ID), ergaenzt um Fakten aus models.json."""
    e: dict = {"name": v["name"], "provider": v["provider"]}
    lim = (src or {}).get("limit") or {}
    if lim.get("context"):
        e["context_window"] = int(lim["context"])
    if lim.get("output"):
        e["output_limit"] = int(lim["output"])
    if src and src.get("release_date"):
        e["release_date"] = src["release_date"]
    if src:
        tags = tag_from_model(src)
        if tags:
            e["tags"] = tags
    return e


def render_family(data: dict, head: str) -> str:
    """models/<family>.yaml im Repo-Stil: name/provider/context_window,
    capabilities als 2er-Indent-Blockliste, Varianten 2er-Indent mit Tags
    als Flow-Liste. Fuehrende Kommentare (head) bleiben erhalten."""
    L = []
    if head.strip():
        L.append(head.rstrip("\n"))
    L.append(f"name: {data['name']}")
    L.append(f"provider: {data['provider']}")
    L.append(f"context_window: {data['context_window']}")
    L.append("capabilities:")
    L += [f"  - {c}" for c in (data.get("capabilities") or [])]
    L.append("variants:")
    for v in data.get("variants", []):
        if not isinstance(v, dict):
            L.append(f"  - {v}")
            continue
        tags = v.pop("tags", None)
        body = yaml.safe_dump(v, sort_keys=False, allow_unicode=True).splitlines()
        out = ["  - " + body[0]] + ["    " + line for line in body[1:]]
        if tags:
            out.append("    tags: [" + ", ".join(tags) + "]")
        L += out
    text = "\n".join(L) + "\n"
    return re.sub(r"(release_date: )'([0-9-]+)'", r"\1\2", text)


def families(write: bool) -> None:
    idx = load_models_index()
    total = done = 0
    for p in sorted((ROOT / "models").glob("*.yaml")):
        text = p.read_text("utf-8")
        data = yaml.safe_load(text) or {}
        m = re.search(r"^name:", text, re.MULTILINE)
        head = text[:m.start()] if m else ""
        variants: list = []
        for v in data.get("variants", []):
            if not isinstance(v, dict):
                variants.append(v)
                continue
            total += 1
            src = idx.get(str(v["name"]).lower())
            if src:
                done += 1
                variants.append(variant_entry(v, src))
            else:
                variants.append(dict(v))
        data["variants"] = variants
        if write:
            p.write_text(render_family(data, head), encoding="utf-8")
    if write:
        print(f"== models/*.yaml angereichert: {done}/{total} Varianten "
              f"mit Fakten aus models.json ==")
    else:
        print(f"== {done}/{total} Varianten koennten angereichert werden "
              f"(dry-run) ==\n")
        for p in sorted((ROOT / "models").glob("*.yaml")):
            d = yaml.safe_load(p.read_text("utf-8"))
            n = sum(1 for v in d.get("variants", [])
                    if isinstance(v, dict) and v["name"].lower() in idx)
            print(f"  {p.stem:<12} {n}/{len(d.get('variants', []))} matched")
    print("Tipp: nach '--write' unbedingt  python3 validate_registry.py -v "
          "laufen lassen.")


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

    g = sub.add_parser("generate", help="fehlende Provider aus dem Mirror anlegen")
    g.add_argument("--write", action="store_true",
                   help="wirklich schreiben (4 Dateien je Provider)")

    f = sub.add_parser("families", help="models/<family>.yaml mit Fakten aus "
                                        "models.json anreichern")
    f.add_argument("--write", action="store_true",
                   help="wirklich in models/*.yaml schreiben")

    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch()
    elif args.cmd == "report":
        report()
    elif args.cmd == "enrich":
        enrich(args.provider or "ALL", args.write, args.limit)
    elif args.cmd == "generate":
        generate(args.write)
    elif args.cmd == "families":
        families(args.write)
    return 0


if __name__ == "__main__":
    sys.exit(main())