#!/usr/bin/env python3
"""
validate_registry.py — Konsistenzpruefung fuer das AI Provider Registry.

Das Repo wird von Hand gepflegt: dieselbe Information steht parallel in den
YAML-Verzeichnissen, in registry.json, in llms.txt und (inkl. hardcodierter
Zaehler + Links) in index.html. Dieses Skript prueft, ob alles synchron ist,
damit beim Hinzufuegen/Loeschen eines Providers nichts vergessen wird.

Aufruf:
    python3 validate_registry.py          # prueft, Exit-Code 1 bei Fehlern
    python3 validate_registry.py -v       # zeigt zusaetzlich, was OK ist

Eignet sich fuer einen pre-commit-Hook oder eine GitHub Action.
"""

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml fehlt:  pip install pyyaml --break-system-packages")

ROOT = Path(__file__).resolve().parent

# Capabilities, die BEWUSST nur im registry.json-Array stehen (keine eigene
# YAML-Datei, kein index.html/llms.txt-Eintrag). Nicht als Fehler werten.
REGISTRY_ONLY_CAPS = {"video", "audio", "realtime"}

errors: list[str] = []
oks: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def ok(msg: str) -> None:
    oks.append(msg)


def stems(subdir: str) -> set[str]:
    """Basisnamen aller *.yaml in einem Verzeichnis (ohne _category.yaml)."""
    d = ROOT / subdir
    if not d.is_dir():
        err(f"Verzeichnis fehlt: {subdir}/")
        return set()
    return {p.stem for p in d.glob("*.yaml") if p.name != "_category.yaml"}


def read_text(name: str) -> str:
    p = ROOT / name
    if not p.exists():
        err(f"Datei fehlt: {name}")
        return ""
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 0. Sind alle YAML-Dateien ueberhaupt parsebar?
# ---------------------------------------------------------------------------
def check_yaml_parses() -> None:
    bad = 0
    for p in ROOT.rglob("*.yaml"):
        if ".git" in p.parts:
            continue
        try:
            yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            err(f"YAML kaputt: {p.relative_to(ROOT)} -> {str(e).splitlines()[0]}")
            bad += 1
    if bad == 0:
        ok("Alle YAML-Dateien parsebar")


# ---------------------------------------------------------------------------
# 1. providers/  <->  registry.json  <->  llms.txt  <->  index.html
# ---------------------------------------------------------------------------
def check_providers() -> None:
    fs = stems("providers")
    if not fs:
        return

    # registry.json providers[].id
    try:
        reg = json.loads(read_text("registry.json") or "{}")
    except json.JSONDecodeError as e:
        err(f"registry.json ist kein gueltiges JSON: {e}")
        reg = {}
    reg_ids = {p.get("id") for p in reg.get("providers", [])}

    missing = fs - reg_ids
    extra = reg_ids - fs
    if missing:
        err(f"registry.json: providers-Array fehlt {sorted(missing)}")
    if extra:
        err(f"registry.json: providers-Array hat Eintrag ohne YAML-Datei {sorted(extra)}")
    if not missing and not extra:
        ok(f"registry.json providers-Array synchron ({len(fs)})")

    # llms.txt
    llms = read_text("llms.txt")
    for name in sorted(fs):
        if f"providers/{name}.yaml" not in llms:
            err(f"llms.txt: providers/{name}.yaml fehlt")
    if all(f"providers/{n}.yaml" in llms for n in fs):
        ok("llms.txt listet alle Provider")

    # index.html: Link-Liste
    html = read_text("index.html")
    linked = set(re.findall(r'providers/([\w.-]+)\.yaml', html))
    miss_html = fs - linked
    if miss_html:
        err(f"index.html: Provider-Links fehlen {sorted(miss_html)}")
    else:
        ok("index.html verlinkt alle Provider")

    # index.html: Stat-Zaehler
    check_stat(html, "Providers", len(fs))

    # index.html free-tier-Badge  ==  pricing.free in YAML  ==  registry.json free
    check_free_flags(fs, html, reg)


def check_free_flags(fs: set[str], html: str, reg: dict) -> None:
    reg_free = {p.get("id"): p.get("free") for p in reg.get("providers", [])}
    # Badges aus index.html: <a href="providers/x.yaml">..</a> ... free tier: yes/no
    badge = dict(re.findall(
        r'providers/([\w.-]+)\.yaml.*?free tier:\s*(yes|no)', html))
    mismatch = 0
    for name in sorted(fs):
        y = yaml.safe_load((ROOT / "providers" / f"{name}.yaml").read_text("utf-8"))
        yfree = bool((y.get("pricing") or {}).get("free", False))
        if name in reg_free and bool(reg_free[name]) != yfree:
            err(f"free-Flag uneinig ({name}): YAML={yfree} vs registry.json={reg_free[name]}")
            mismatch += 1
        if name in badge and (badge[name] == "yes") != yfree:
            err(f"free-Badge uneinig ({name}): YAML={yfree} vs index.html='{badge[name]}'")
            mismatch += 1
    if mismatch == 0:
        ok("free-Flags konsistent (YAML / registry.json / index.html)")


# ---------------------------------------------------------------------------
# 2. models/  <->  llms.txt  <->  index.html   (NICHT in registry.json)
# ---------------------------------------------------------------------------
def check_models() -> None:
    fs = stems("models")
    if not fs:
        return
    llms = read_text("llms.txt")
    html = read_text("index.html")
    for name in sorted(fs):
        if f"models/{name}.yaml" not in llms:
            err(f"llms.txt: models/{name}.yaml fehlt")
        if f"models/{name}.yaml" not in html:
            err(f"index.html: models/{name}.yaml Link fehlt")
    if all(f"models/{n}.yaml" in llms for n in fs) and \
       all(f"models/{n}.yaml" in html for n in fs):
        ok(f"models/ synchron mit llms.txt + index.html ({len(fs)})")
    check_stat(html, "Model Families", len(fs))


# ---------------------------------------------------------------------------
# 3. capabilities/  <->  registry.json  <->  llms.txt  <->  index.html
# ---------------------------------------------------------------------------
def check_capabilities() -> None:
    fs = stems("capabilities")
    if not fs:
        return
    try:
        reg = json.loads(read_text("registry.json") or "{}")
    except json.JSONDecodeError:
        reg = {}
    reg_caps = set(reg.get("capabilities", []))

    # Jede YAML-Capability muss im registry-Array stehen.
    missing = fs - reg_caps
    if missing:
        err(f"registry.json: capabilities-Array fehlt {sorted(missing)}")
    # Umgekehrt duerfen nur die bewussten Extras ohne YAML existieren.
    unexpected = (reg_caps - fs) - REGISTRY_ONLY_CAPS
    if unexpected:
        err(f"registry.json: capabilities ohne YAML und nicht als Extra deklariert "
            f"{sorted(unexpected)} (falls gewollt -> REGISTRY_ONLY_CAPS ergaenzen)")
    if not missing and not unexpected:
        ok(f"capabilities-Array synchron (YAML {len(fs)} + Extras "
           f"{sorted(reg_caps & REGISTRY_ONLY_CAPS)})")

    llms = read_text("llms.txt")
    html = read_text("index.html")
    for name in sorted(fs):
        if f"capabilities/{name}.yaml" not in llms:
            err(f"llms.txt: capabilities/{name}.yaml fehlt")
        if f"capabilities/{name}.yaml" not in html:
            err(f"index.html: capabilities/{name}.yaml Link fehlt")
    check_stat(html, "Capabilities", len(fs))


# ---------------------------------------------------------------------------
# 4. api_spec: wenn lokaler Pfad -> Datei muss existieren
# ---------------------------------------------------------------------------
def check_api_specs() -> None:
    problems = 0
    for p in (ROOT / "providers").glob("*.yaml"):
        y = yaml.safe_load(p.read_text("utf-8")) or {}
        spec = y.get("api_spec")
        if isinstance(spec, str) and not spec.startswith(("http://", "https://")):
            if not (ROOT / spec).exists():
                err(f"{p.name}: api_spec zeigt auf '{spec}', Datei fehlt")
                problems += 1
    if problems == 0:
        ok("Lokale api_spec-Pfade existieren")


# ---------------------------------------------------------------------------
def check_stat(html: str, label: str, expected: int) -> None:
    m = re.search(
        r'stat-value">\s*(\d+)\s*</div>\s*<div class="stat-label">' + re.escape(label),
        html)
    if not m:
        err(f"index.html: Stat-Zaehler '{label}' nicht gefunden")
        return
    got = int(m.group(1))
    if got != expected:
        err(f"index.html: Stat '{label}' = {got}, tatsaechlich {expected}")
    else:
        ok(f"index.html Stat '{label}' = {expected}")


def main() -> int:
    verbose = "-v" in sys.argv
    check_yaml_parses()
    check_providers()
    check_models()
    check_capabilities()
    check_api_specs()

    if verbose:
        for line in oks:
            print(f"  OK   {line}")
    if errors:
        print(f"\n{len(errors)} Problem(e):")
        for line in errors:
            print(f"  FEHLER  {line}")
        print("\nRegistry NICHT synchron.")
        return 1
    print(f"\nAlles synchron ({len(oks)} Checks bestanden).")
    return 0


if __name__ == "__main__":
    sys.exit(main())