import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).parents[1]
FILTER_SPEC = importlib.util.spec_from_file_location(
    "truenas_names", ROOT / "ansible/filter_plugins/truenas_names.py"
)
names = importlib.util.module_from_spec(FILTER_SPEC)
FILTER_SPEC.loader.exec_module(names)


class DockerMainProfileTests(unittest.TestCase):
    def test_hostname_is_derived_from_registered_vm_name(self):
        self.assertEqual(names.truenas_hostname("docker-main_IP40"), "docker-main-ip40")
        self.assertEqual(names.truenas_hostname("DockerMain_IP120"), "dockermain-ip120")

    def test_hostname_filter_normalizes_and_limits_input(self):
        value = names.truenas_hostname("My__VM!!_IP40")
        self.assertEqual(value, "my-vm-ip40")
        self.assertLessEqual(len(names.truenas_hostname("a" * 80)), 63)

    def test_portainer_is_the_only_compose_service(self):
        compose_path = ROOT / "ansible/core_profiles/databases/files/compose.yml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        self.assertEqual(set(compose["services"]), {"portainer"})
        portainer = compose["services"]["portainer"]
        self.assertEqual(portainer["image"], "portainer/portainer-ce:latest")
        self.assertIn("9000:9000", portainer["ports"])
        self.assertIn("/home/fenkil/pcData/portainer/data:/data", portainer["volumes"])

    def test_pgvector_compose_matches_database_contract(self):
        template = (
            ROOT / "ansible/core_profiles/databases/templates/postgres-compose.yml.j2"
        ).read_text(encoding="utf-8")
        variables = yaml.safe_load(
            (ROOT / "ansible/core_profiles/databases/vars.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("pgvector:", template)
        self.assertIn("restart: unless-stopped", template)
        self.assertIn("pgvector.env", template)
        self.assertIn("{{ docker_main_postgres_bind_address }}:5432:5432", template)
        self.assertIn("./init.sql:/docker-entrypoint-initdb.d/init.sql:ro", template)
        self.assertIn("pg_isready", template)
        self.assertEqual(variables["docker_main_postgres_image"], "pgvector/pgvector:0.8.5-pg17")
        self.assertEqual(variables["docker_main_database_directory"], "{{ docker_main_data_root }}/pgvector")
        self.assertEqual(variables["docker_main_postgres_database"], "pi_memory")
        self.assertEqual(variables["docker_main_postgres_user"], "fenkil")
        self.assertEqual(variables["docker_main_postgres_password"], "fenkil")
        self.assertEqual(variables["docker_main_postgres_uid"], 999)
        self.assertEqual(variables["docker_main_postgres_gid"], 999)
        init_sql = (ROOT / "ansible/core_profiles/databases/files/init.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector;", init_sql)
        playbook = (ROOT / "ansible/core_profiles/databases/site.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("mode: \"0644\"", playbook)
        self.assertIn("community.docker.docker_container_exec:", playbook)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector;", playbook)

    def test_backup_script_guards_nfs_and_restarts_containers(self):
        template = (
            ROOT / "ansible/roles/pcdata_backup/templates/backup-pcdata.sh.j2"
        ).read_text(encoding="utf-8")
        self.assertLess(template.index("findmnt"), template.index("docker compose --project-directory"))
        self.assertIn("trap restart_projects EXIT INT TERM", template)
        self.assertIn("rsync --archive --delete --numeric-ids", template)

    def test_autofs_roles_preserve_each_others_entries(self):
        media_tasks = (
            ROOT / "ansible/roles/media_autofs/tasks/main.yml"
        ).read_text(encoding="utf-8")
        backup_tasks = (
            ROOT / "ansible/roles/pcdata_backup/tasks/main.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("ansible.builtin.lineinfile:", media_tasks)
        self.assertIn("ansible.builtin.lineinfile:", backup_tasks)
        self.assertNotIn("content: |", media_tasks)

    def test_shared_storage_has_expected_protection_and_retention(self):
        main = (ROOT / "opentofu/backup-storage/main.tf").read_text(encoding="utf-8")
        self.assertIn('backup_dataset = "${var.backup_parent_dataset}/dataOnly"', main)
        self.assertGreaterEqual(main.count("prevent_destroy = true"), 3)
        self.assertIn('networks     = var.backup_networks', main)
        self.assertIn('lifetime_value = 30', main)
        self.assertIn('lifetime_unit  = "DAY"', main)
        self.assertIn('schedule       = "0 2 * * *"', main)

    def test_core_setup_checks_storage_before_assignment_and_never_applies_it(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        setup = makefile.split("setup-core: require-vm", 1)[1].split("\nbackup-now:", 1)[0]
        self.assertLess(setup.index("core-storage-preflight"), setup.index("inventory"))
        self.assertLess(setup.index("core-storage-preflight"), setup.index("resolve --vm"))
        self.assertNotIn("backup-storage-apply", setup)

    def test_profile_change_checks_required_storage_before_assignment(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        change = makefile.split("change-core-profile: require-vm require-profile", 1)[1].split(
            "\nsuggest:", 1
        )[0]
        self.assertLess(change.index("requires-backup"), change.index("core_profiles.py change"))
        self.assertIn("backup-storage-check", change)
        self.assertNotIn("backup-storage-apply", change)

    def test_databases_backup_is_explicitly_opt_in(self):
        metadata_path = ROOT / "ansible/core_profiles/databases/profile.json"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        self.assertFalse(metadata["requires_backup_storage"])
        variables = yaml.safe_load(
            (ROOT / "ansible/core_profiles/databases/vars.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(variables["docker_main_backup_enabled"])
        playbook = (ROOT / "ansible/core_profiles/databases/site.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("when: docker_main_backup_enabled | bool", playbook)


if __name__ == "__main__":
    unittest.main()
