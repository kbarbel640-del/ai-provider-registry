#!/usr/bin/env python3
"""Split providers.yaml and dork_templates.yaml into per-file OSINT Provider Registry."""

import os
import json
import yaml
from collections import OrderedDict

BASE = "/home/ckmaenn/Desktop/PRIV8_DBs/mcp_osint/osint-providers"

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)

def write_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"  {path}")

def split_providers(data):
    """Split providers.yaml into per-category/provider YAML files."""
    entry_points = []

    categories = {
        "internet-scanner": "Internet Scanner / Attack Surface",
        "threat-intel": "Threat Intelligence / Malware / Reputation",
        "search-engines": "Search Engines & Web Search",
        "dns-domain": "DNS / Domain / Subdomain Enumeration",
        "email-leaks": "Email / People / Leaks",
        "infrastructure": "Infrastructure / Network / Geolocation",
        "web-archive": "Web Archive / Source Code / Tech Detection",
        "code-search": "Code Search / Repository Intel / Secret Hunting",
    }

    # Map YAML keys to directory names
    key_to_dir = {
        "internet_scanner": "internet-scanner",
        "threat_intel": "threat-intel",
        "search_engines": "search-engines",
        "dns_domain": "dns-domain",
        "email_leaks": "email-leaks",
        "infrastructure": "infrastructure",
        "web_archive": "web-archive",
        "code_search": "code-search",
    }

    dir_to_label = {v: k for k, v in key_to_dir.items()}

    for yaml_key, dir_name in key_to_dir.items():
        providers = data.get(yaml_key, [])
        if not providers:
            continue
        label = categories.get(dir_name, dir_name)
        cat_dir = os.path.join(BASE, dir_name)
        os.makedirs(cat_dir, exist_ok=True)

        for p in providers:
            prov_id = p.get("id", "unknown")
            prov_file = os.path.join(cat_dir, f"{prov_id}.yaml")
            # Add category context
            prov_data = dict(p)
            prov_data["_category"] = dir_name
            prov_data["_category_label"] = label
            write_yaml(prov_file, prov_data)
            entry_points.append({
                "id": prov_id,
                "name": p.get("name", prov_id),
                "category": dir_name,
                "category_label": label,
                "path": f"{dir_name}/{prov_id}.yaml",
                "free_tier": p.get("free_tier", False),
                "priority": p.get("priority", 5),
                "rate_limit": p.get("rate_limit", "N/A"),
                "free_tier_description": p.get("free_tier_description", ""),
            })

        # Category-level YAML with all providers in that category
        cat_file = os.path.join(BASE, dir_name, "_category.yaml")
        write_yaml(cat_file, {
            "category": dir_name,
            "label": label,
            "provider_count": len(providers),
            "providers": [p.get("id") for p in providers]
        })

    return entry_points


def split_dork_templates(data):
    """Split dork_templates.yaml into per-template YAML files.
    The file is a flat list of template dicts."""
    templates_dir = os.path.join(BASE, "dork-templates")
    os.makedirs(templates_dir, exist_ok=True)

    entry_points = []
    for tmpl in data if isinstance(data, list) else data.get("dork_templates", []):
        if not isinstance(tmpl, dict):
            continue
        tmpl_id = tmpl.get("id", "unknown")
        tmpl_file = os.path.join(templates_dir, f"{tmpl_id}.yaml")
        write_yaml(tmpl_file, dict(tmpl, id=tmpl_id))
        entry_points.append({
            "id": tmpl_id,
            "name": tmpl.get("name", tmpl_id),
            "risk": tmpl.get("risk", "unknown"),
            "path": f"dork-templates/{tmpl_id}.yaml",
        })

    # Category file
    cat_file = os.path.join(templates_dir, "_category.yaml")
    write_yaml(cat_file, {
        "category": "dork-templates",
        "label": "Dork Templates (Use-Case Definitions)",
        "template_count": len(entry_points),
        "templates": [e["id"] for e in entry_points]
    })
    return entry_points


def create_registry_json(providers, dork_templates):
    """Create osint-registry.json."""
    registry = OrderedDict([
        ("metadata", OrderedDict([
            ("name", "OSINT Provider Registry"),
            ("description", "A structured registry of OSINT/search platforms with API details, free tier info, and dork syntax, optimized for LLM and security researcher consumption."),
            ("version", "1.0.0"),
            ("last_updated", "2026-06-26"),
            ("llms_txt", "osint-llms.txt"),
        ])),
        ("categories", {}),
        ("dork_templates", []),
        ("total_providers", len(providers)),
        ("total_dork_templates", len(dork_templates)),
    ])

    # Group providers by category
    cats = {}
    for p in providers:
        cat = p["category"]
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(p["id"])

    registry["categories"] = OrderedDict(sorted(cats.items()))
    registry["dork_templates"] = [t["id"] for t in dork_templates]

    reg_path = os.path.join(BASE, "osint-registry.json")
    with open(reg_path, "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    print(f"  {reg_path}")


def create_llms_txt(providers, dork_templates):
    """Create osint-llms.txt entry point."""
    lines = [
        "# OSINT Provider Registry Index",
        f"# https://kbarbel640-del.github.io/ai-provider-registry/osint-providers/",
        "# For LLM consumption - discover all OSINT provider files in the registry.",
        "",
        "# ============================================================",
        "# QUICK START",
        "# ============================================================",
        "# This registry catalogs OSINT/search platforms with:",
        "# - API endpoints & authentication methods",
        "# - Free tier availability & rate limits",
        "# - Dork/search syntax per platform",
        "# - Use-case dork templates",
        "#",
        "# All data is in per-provider YAML files organized by category.",
        "# The registry.json has the full machine-readable index.",
        "",
        "# ============================================================",
        "# PROVIDERS BY CATEGORY",
        "# ============================================================",
        "",
    ]

    cats = {}
    for p in providers:
        cat = p["category"]
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(p)

    for cat_name in ["internet-scanner", "threat-intel", "search-engines", "dns-domain", "email-leaks", "infrastructure", "web-archive", "code-search"]:
        cat_providers = cats.get(cat_name, [])
        if not cat_providers:
            continue
        # Capitalize
        label = cat_name.replace("-", " ").title()
        lines.append(f"## {label}")
        lines.append(f"# ({len(cat_providers)} providers)")
        cat_dir = cat_name
        for p in sorted(cat_providers, key=lambda x: x["priority"]):
            free_tag = " [FREE]" if p.get("free_tier") else ""
            lines.append(f"{cat_dir}/{p['id']}.yaml  # {p['name']}{free_tag} - {p.get('rate_limit', 'N/A')}")
        lines.append("")

    lines += [
        "# ============================================================",
        "# DORK TEMPLATES",
        "# ============================================================",
        "# ({len(dork_templates)} templates)",
        "",
    ]
    for t in sorted(dork_templates, key=lambda x: x["risk"]):
        risk_icon = {"critical": "[CRIT]", "high": "[HIGH]", "medium": "[MED]"}.get(t.get("risk", ""), "")
        lines.append(f"dork-templates/{t['id']}.yaml  # {risk_icon} {t['name']}")
    lines.append("")

    lines += [
        "# ============================================================",
        "# CATEGORY INDEXES",
        "# ============================================================",
    ]
    for cat_name in ["internet-scanner", "threat-intel", "search-engines", "dns-domain", "email-leaks", "infrastructure", "web-archive", "code-search", "dork-templates"]:
        lines.append(f"{cat_name}/_category.yaml")

    txt_path = os.path.join(BASE, "osint-llms.txt")
    with open(txt_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  {txt_path}")


def main():
    print("Loading providers.yaml...")
    providers_data = load_yaml("/home/ckmaenn/Desktop/PRIV8_DBs/mcp_osint/providers.yaml")

    print("Loading dork_templates.yaml...")
    dork_data = load_yaml("/home/ckmaenn/Desktop/PRIV8_DBs/mcp_osint/dork_templates.yaml")

    print("\nSplitting providers...")
    providers = split_providers(providers_data)

    print("\nSplitting dork templates...")
    dork_templates = split_dork_templates(dork_data)

    print("\nCreating registry.json...")
    create_registry_json(providers, dork_templates)

    print("\nCreating osint-llms.txt...")
    create_llms_txt(providers, dork_templates)

    print(f"\nDone! {len(providers)} providers, {len(dork_templates)} dork templates")


if __name__ == "__main__":
    main()
