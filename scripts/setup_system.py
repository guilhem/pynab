#!/usr/bin/env python3
"""
System setup for Pynab.

This script handles:
- PostgreSQL database configuration
- Nginx web server configuration
- systemd service installation and activation
- Log rotation setup
- Avahi service advertising
- Django migrations and localization

Can be run with or without sudo depending on operations needed.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SystemSetupError(Exception):
    """Exception raised for system setup errors."""

    pass


class SystemSetup:
    """Handle system configuration for Pynab."""

    def __init__(self, root_dir: Path, venv_dir: Optional[Path] = None):
        self.root_dir = root_dir
        self.venv_dir = venv_dir or (root_dir / "venv")

        if not self.venv_dir.exists():
            raise SystemSetupError(
                f"Virtual environment not found at {self.venv_dir}. "
                "Run 'python -m scripts.install' first."
            )

    def _run_command(self, cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
        """Run a command with error handling."""
        logger.debug(f"Running: {' '.join(cmd)}")
        try:
            return subprocess.run(cmd, check=True, **kwargs)
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}")
            raise SystemSetupError(f"Command failed: {' '.join(cmd)}")

    def setup_postgresql(self):
        """Configure PostgreSQL database."""
        logger.info("Setting up PostgreSQL database...")

        # Check if database exists
        result = subprocess.run(
            ["psql", "-U", "pynab", "-c", ""], capture_output=True, text=True
        )

        if result.returncode != 0:
            logger.info("Database doesn't exist, creating...")

            # Configure PostgreSQL for trusted local access
            pg_hba_files = list(Path("/etc/postgresql").glob("*/main/pg_hba.conf"))
            if not pg_hba_files:
                raise SystemSetupError("PostgreSQL configuration file not found")

            for pg_hba in pg_hba_files:
                logger.info(f"Configuring {pg_hba} for trusted access")

                # Backup original
                backup = pg_hba.with_suffix(".conf.orig")
                if not backup.exists():
                    self._run_command(["sudo", "cp", str(pg_hba), str(backup)])

                # Replace peer with trust for local connections
                self._run_command(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-E",
                        r"s/^(local +all +all +)peer$/\1trust/",
                        str(pg_hba),
                    ]
                )

            # Restart PostgreSQL
            logger.info("Restarting PostgreSQL...")
            self._run_command(["sudo", "systemctl", "restart", "postgresql"])

            # Create user and database
            logger.info("Creating pynab user and database...")
            self._run_command(
                [
                    "sudo",
                    "-u",
                    "postgres",
                    "psql",
                    "-U",
                    "postgres",
                    "-c",
                    "CREATE USER pynab",
                ]
            )
            self._run_command(
                [
                    "sudo",
                    "-u",
                    "postgres",
                    "psql",
                    "-U",
                    "postgres",
                    "-c",
                    "CREATE DATABASE pynab OWNER=pynab LC_COLLATE='C' LC_CTYPE='C' ENCODING='UTF-8' TEMPLATE template0",
                ]
            )
            self._run_command(
                [
                    "sudo",
                    "-u",
                    "postgres",
                    "psql",
                    "-U",
                    "postgres",
                    "-c",
                    "ALTER ROLE pynab CREATEDB",
                ]
            )

            logger.info("✓ PostgreSQL database created")
        else:
            logger.info("✓ PostgreSQL database already exists")

    def setup_nginx(self):
        """Configure Nginx web server."""
        logger.info("Setting up Nginx...")

        # Generate nginx config from template
        template = self.root_dir / "nabweb" / "nginx-site.conf"
        if not template.exists():
            raise SystemSetupError(f"Nginx template not found: {template}")

        with open(template, "r") as f:
            config = f.read()

        # Replace paths
        config = config.replace("/opt/pynab", str(self.root_dir))

        # Write to sites-enabled
        target = Path("/etc/nginx/sites-enabled/pynab")

        # Check if update needed
        needs_update = True
        if target.exists():
            with open(target, "r") as f:
                if f.read() == config:
                    needs_update = False
                    logger.info("✓ Nginx configuration already up to date")

        if needs_update:
            logger.info("Installing Nginx configuration...")

            # Remove default site if it's a symlink
            default_site = Path("/etc/nginx/sites-enabled/default")
            if default_site.is_symlink():
                self._run_command(["sudo", "rm", str(default_site)])

            # Write new config
            with open("/tmp/nginx-site.conf", "w") as f:
                f.write(config)
            self._run_command(["sudo", "mv", "/tmp/nginx-site.conf", str(target)])
            self._run_command(["sudo", "chown", "root:root", str(target)])

            # Restart nginx
            logger.info("Restarting Nginx...")
            self._run_command(["sudo", "systemctl", "restart", "nginx"])

            logger.info("✓ Nginx configured")

    def run_migrations(self):
        """Run Django database migrations."""
        logger.info("Running database migrations...")

        manage_py = self.root_dir / "manage.py"
        python = self.venv_dir / "bin" / "python"

        self._run_command([str(python), str(manage_py), "migrate"])

        logger.info("✓ Migrations completed")

    def compile_localization(self):
        """Compile localization messages."""
        logger.info("Compiling localization messages...")

        django_admin = self.venv_dir / "bin" / "django-admin"

        locales = [
            "-l",
            "fr_FR",
            "-l",
            "de_DE",
            "-l",
            "en_US",
            "-l",
            "en_GB",
            "-l",
            "it_IT",
            "-l",
            "es_ES",
            "-l",
            "ja_jp",
            "-l",
            "pt_BR",
            "-l",
            "de",
            "-l",
            "en",
            "-l",
            "es",
            "-l",
            "fr",
            "-l",
            "it",
            "-l",
            "ja",
            "-l",
            "pt",
        ]

        # Compile messages for each module
        for module_dir in self.root_dir.glob("nab*/"):
            locale_dir = module_dir / "locale"
            if locale_dir.exists():
                logger.info(f"Compiling messages for {module_dir.name}")
                self._run_command(
                    [str(django_admin), "compilemessages"] + locales, cwd=module_dir
                )

        logger.info("✓ Localization compiled")

    def setup_systemd_services(self):
        """Install and enable systemd services."""
        logger.info("Setting up systemd services...")

        # Find all service files
        service_files = list(self.root_dir.glob("*/*.service"))
        service_files.append(self.root_dir / "nabd" / "nabd.socket")

        if not service_files:
            logger.warning("No service files found")
            return

        for service_file in service_files:
            name = service_file.name
            logger.info(f"Installing {name}")

            # Read and replace paths
            with open(service_file, "r") as f:
                content = f.read()

            content = content.replace("/opt/pynab", str(self.root_dir))
            content = content.replace("/home/pi/pynab", str(self.root_dir))

            # Write to systemd directory
            systemd_path = Path("/lib/systemd/system") / name
            with open("/tmp/" + name, "w") as f:
                f.write(content)

            self._run_command(["sudo", "mv", f"/tmp/{name}", str(systemd_path)])
            self._run_command(["sudo", "chown", "root:root", str(systemd_path)])
            self._run_command(["sudo", "chmod", "644", str(systemd_path)])

            # Enable service
            self._run_command(["sudo", "systemctl", "enable", name])

        # Install shutdown script
        shutdown_script = self.root_dir / "nabboot" / "nabboot.py"
        if shutdown_script.exists():
            logger.info("Installing shutdown script...")
            with open(shutdown_script, "r") as f:
                content = f.read()

            content = content.replace("/opt/pynab", str(self.root_dir))

            target = Path("/lib/systemd/system-shutdown/nabboot.py")
            with open("/tmp/nabboot.py", "w") as f:
                f.write(content)

            self._run_command(["sudo", "mv", "/tmp/nabboot.py", str(target)])
            self._run_command(["sudo", "chown", "root:root", str(target)])
            self._run_command(["sudo", "chmod", "+x", str(target)])

        logger.info(f"✓ Installed {len(service_files)} services")

    def setup_log_rotation(self):
        """Setup log rotation for Pynab."""
        logger.info("Setting up log rotation...")

        logrotate_config = """
/var/log/nab*.log {
  weekly
  rotate 4
  missingok
  notifempty
  copytruncate
  delaycompress
  compress
}
"""

        target = Path("/etc/logrotate.d/pynab")
        with open("/tmp/pynab-logrotate", "w") as f:
            f.write(logrotate_config)

        self._run_command(["sudo", "mv", "/tmp/pynab-logrotate", str(target)])
        self._run_command(["sudo", "chown", "root:root", str(target)])
        self._run_command(["sudo", "chmod", "644", str(target)])

        logger.info("✓ Log rotation configured")

    def setup_avahi(self):
        """Setup Avahi service advertising."""
        logger.info("Setting up Avahi service advertising...")

        # Check if avahi is installed
        avahi_services_dir = Path("/etc/avahi/services")
        if not avahi_services_dir.exists():
            logger.warning(
                "Avahi not installed or /etc/avahi/services does not exist, skipping"
            )
            return

        # Pynab web interface service
        pynab_service = avahi_services_dir / "pynab.service"
        if not pynab_service.exists():
            logger.info("Creating Pynab Avahi service...")
            service_xml = """<?xml version="1.0" standalone='no'?><!--*-nxml-*-->
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<!-- See avahi.service(5) for more information about this configuration file -->
<service-group>
  <name replace-wildcards="yes">Nabaztag rabbit (%h)</name>
  <service>
    <type>_http._tcp</type>
    <port>80</port>
    <txt-record>vendor=violet</txt-record>
    <txt-record>model=tag:tag:tag</txt-record>
  </service>
</service-group>
"""
            with open("/tmp/pynab.service", "w", encoding="utf-8") as f:
                f.write(service_xml)

            self._run_command(["sudo", "mv", "/tmp/pynab.service", str(pynab_service)])
            self._run_command(["sudo", "chown", "root:root", str(pynab_service)])

        # NabBlockly service
        nabblockly_service = avahi_services_dir / "nabblocky.service"
        if not nabblockly_service.exists():
            logger.info("Creating NabBlockly Avahi service...")
            service_xml = """<?xml version="1.0" standalone='no'?><!--*-nxml-*-->
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<!-- See avahi.service(5) for more information about this configuration file -->
<service-group>
  <name replace-wildcards="yes">NabBlockly (%h)</name>
  <service>
    <type>_http._tcp</type>
    <port>8080</port>
    <txt-record>vendor=Paul Guyot</txt-record>
    <txt-record>model=tag:tag:tag</txt-record>
  </service>
</service-group>
"""
            with open("/tmp/nabblocky.service", "w", encoding="utf-8") as f:
                f.write(service_xml)

            self._run_command(
                ["sudo", "mv", "/tmp/nabblocky.service", str(nabblockly_service)]
            )
            self._run_command(["sudo", "chown", "root:root", str(nabblockly_service)])

        logger.info("✓ Avahi services configured")

    def start_services(self):
        """Start Pynab services."""
        logger.info("Starting Pynab services...")

        # Start nabd socket and service
        self._run_command(["sudo", "systemctl", "start", "nabd.socket"])
        self._run_command(["sudo", "systemctl", "start", "nabd.service"])

        # Start all nab*d services except nabd and nabweb
        for service_file in self.root_dir.glob("*/*.service"):
            name = service_file.name
            if name not in ["nabd.service", "nabweb.service"]:
                logger.info(f"Starting {name}")
                self._run_command(["sudo", "systemctl", "start", name])

        # Start nabweb last
        self._run_command(["sudo", "systemctl", "start", "nabweb.service"])

        logger.info("✓ Services started")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup system configuration for Pynab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script configures system components for Pynab.
Some operations require sudo privileges.

Examples:
  # Full system setup (requires sudo)
  sudo python -m scripts.setup_system

  # Only database and migrations (no sudo needed if DB exists)
  python -m scripts.setup_system --database --migrations

  # Setup services without starting them
  sudo python -m scripts.setup_system --services --no-start

  # Dry run to see what would be done
  sudo python -m scripts.setup_system --dry-run
        """,
    )

    parser.add_argument(
        "--venv", type=Path, help="Path to virtual environment (default: ./venv)"
    )

    parser.add_argument(
        "--database", action="store_true", help="Setup PostgreSQL database only"
    )

    parser.add_argument("--nginx", action="store_true", help="Setup Nginx only")

    parser.add_argument("--migrations", action="store_true", help="Run migrations only")

    parser.add_argument(
        "--services", action="store_true", help="Setup systemd services only"
    )

    parser.add_argument(
        "--no-start",
        action="store_true",
        help="Do not start services after installation",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine root directory
    root_dir = Path(__file__).parent.parent.resolve()

    if args.dry_run:
        logger.info("=== DRY RUN MODE ===")
        logger.info("Would perform system setup based on selected options")
        return

    try:
        setup = SystemSetup(root_dir, args.venv)

        # Determine what to setup
        setup_all = not (
            args.database or args.nginx or args.migrations or args.services
        )

        if setup_all or args.database:
            setup.setup_postgresql()

        if setup_all or args.migrations:
            setup.run_migrations()

        if setup_all:
            setup.compile_localization()

        if setup_all or args.nginx:
            setup.setup_nginx()

        if setup_all or args.services:
            setup.setup_systemd_services()
            setup.setup_log_rotation()
            setup.setup_avahi()

        if (setup_all or args.services) and not args.no_start:
            setup.start_services()

        logger.info("\n" + "=" * 60)
        logger.info("System setup completed!")
        logger.info("=" * 60)

        if not args.no_start:
            logger.info("\nPynab services are now running")
            logger.info("Web interface: http://localhost or http://<hostname>.local")
        else:
            logger.info("\nTo start services:")
            logger.info("  sudo systemctl start nabd.socket")
            logger.info("  sudo systemctl start nabweb.service")

    except SystemSetupError as e:
        logger.error(f"Setup failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nSetup cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
