import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_zap_rules.py"
SPEC = importlib.util.spec_from_file_location("check_zap_rules", SCRIPT_PATH)
zap_rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(zap_rules)


class ZapRulesTests(unittest.TestCase):
    def write_rules(self, content):
        temporary_directory = tempfile.TemporaryDirectory()
        path = Path(temporary_directory.name) / "rules.tsv"
        path.write_text(content, encoding="utf-8")
        return temporary_directory, path

    def test_repository_policy_is_valid(self):
        project_root = SCRIPT_PATH.parents[1]
        rules = zap_rules.parse_rules(
            project_root / ".zap" / "rules.tsv"
        )

        zap_rules.validate_policy(rules)

    def test_spaces_do_not_replace_tabs(self):
        directory, path = self.write_rules(
            "10010 FAIL Cookie No HttpOnly Flag\n"
        )

        try:
            with self.assertRaises(ValueError):
                zap_rules.parse_rules(path)
        finally:
            directory.cleanup()

    def test_missing_blocking_rule_is_rejected(self):
        rules = {
            rule_id: "FAIL"
            for rule_id in zap_rules.REQUIRED_FAIL_RULES
            if rule_id != "10038"
        }
        rules["10035"] = "IGNORE"

        with self.assertRaises(ValueError):
            zap_rules.validate_policy(rules)

    def test_hsts_must_be_ignored_only_for_ephemeral_http(self):
        rules = {
            rule_id: "FAIL"
            for rule_id in zap_rules.REQUIRED_FAIL_RULES
        }
        rules["10035"] = "FAIL"

        with self.assertRaises(ValueError):
            zap_rules.validate_policy(rules)


if __name__ == "__main__":
    unittest.main()
