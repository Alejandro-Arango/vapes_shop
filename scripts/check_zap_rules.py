#!/usr/bin/env python3
"""Valida la politica bloqueante usada por OWASP ZAP Baseline."""

import sys
from pathlib import Path


ALLOWED_ACTIONS = {"FAIL", "WARN", "INFO", "IGNORE"}
REQUIRED_FAIL_RULES = {
    "10010",
    "10011",
    "10019",
    "10020",
    "10021",
    "10023",
    "10038",
    "10063",
    "90022",
}


def parse_rules(path):
    rules = {}

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        parts = raw_line.split("\t", maxsplit=2)

        if len(parts) != 3:
            raise ValueError(
                f"Linea {line_number}: usa rule_id, accion y descripcion separados por tab."
            )

        rule_id, action, description = (part.strip() for part in parts)

        if not rule_id.isdigit():
            raise ValueError(f"Linea {line_number}: rule_id invalido.")

        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"Linea {line_number}: accion invalida {action}.")

        if not description:
            raise ValueError(f"Linea {line_number}: falta descripcion.")

        if rule_id in rules:
            raise ValueError(f"Linea {line_number}: regla duplicada {rule_id}.")

        rules[rule_id] = action

    return rules


def validate_policy(rules):
    missing_failures = sorted(
        rule_id
        for rule_id in REQUIRED_FAIL_RULES
        if rules.get(rule_id) != "FAIL"
    )

    if missing_failures:
        raise ValueError(
            "Reglas obligatorias sin FAIL: " + ", ".join(missing_failures)
        )

    if rules.get("10035") != "IGNORE":
        raise ValueError(
            "La regla HSTS 10035 debe quedar IGNORE en el DAST HTTP efimero."
        )


def main():
    project_root = Path(__file__).resolve().parents[1]
    rules_path = project_root / ".zap" / "rules.tsv"

    try:
        rules = parse_rules(rules_path)
        validate_policy(rules)
    except (OSError, ValueError) as exc:
        print(f"Politica ZAP invalida: {exc}", file=sys.stderr)
        return 1

    print(f"Politica ZAP valida: {len(rules)} reglas configuradas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
