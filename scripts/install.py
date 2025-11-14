#!/usr/bin/env python3
"""
Modern modular installation system for Pynab.

This installer follows best practices:
- Uses pyproject.toml for dependency management
- Modular architecture with separate concerns
- Interactive and non-interactive modes
- Idempotent operations
- Proper error handling and logging
"""

import argparse
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class InstallationError(Exception):
    """Base exception for installation errors."""

    pass


class PynabInstaller:
    """Main installer class for Pynab."""

    def __init__(self, root_dir: Path, interactive: bool = True):
        self.root_dir = root_dir
        self.interactive = interactive
        self.python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        self.machine = platform.machine()
        self.system = platform.system()

    def check_platform(self) -> bool:
        """Check if the platform is supported."""
        if self.system != "Linux":
            logger.warning(f"Platform {self.system} may not be fully supported")
            return False

        # Check if Raspberry Pi
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                if "Raspberry Pi" not in cpuinfo:
                    logger.warning("This installation is optimized for Raspberry Pi")
                    return self.interactive and self._confirm("Continue anyway?")
        except FileNotFoundError:
            logger.warning("Cannot detect hardware platform")

        return True

    def check_python_version(self) -> bool:
        """Check if Python version is supported."""
        major, minor = sys.version_info[:2]
        if major < 3 or (major == 3 and minor < 7):
            logger.error(
                f"Python {major}.{minor} is not supported. Requires Python 3.7+"
            )
            return False

        if minor not in [7, 9, 11]:
            logger.warning(f"Python {major}.{minor} may not be fully tested")

        logger.info(f"Python {major}.{minor} detected")
        return True

    def _confirm(self, message: str) -> bool:
        """Ask user for confirmation in interactive mode."""
        if not self.interactive:
            return True

        response = input(f"{message} [y/N]: ").strip().lower()
        return response in ["y", "yes"]

    def _run_command(
        self, cmd: List[str], check: bool = True, capture_output: bool = False, env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Run a command with error handling."""
        logger.info(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, check=check, capture_output=capture_output, text=True, env=env
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}")
            if e.stderr:
                logger.error(f"Error output: {e.stderr}")
            raise InstallationError(f"Command failed: {' '.join(cmd)}")

    def setup_venv(self, venv_path: Path) -> Path:
        """Create or verify virtual environment."""
        if venv_path.exists():
            logger.info(f"Virtual environment already exists at {venv_path}")
            # Check if it's the right Python version
            pyvenv_cfg = venv_path / "pyvenv.cfg"
            if pyvenv_cfg.exists():
                with open(pyvenv_cfg, "r") as f:
                    content = f.read()
                    if f"version = {self.python_version}" not in content:
                        logger.warning("Virtual environment Python version mismatch")
                        if self._confirm("Recreate virtual environment?"):
                            import shutil

                            shutil.rmtree(venv_path)
                        else:
                            return venv_path

        if not venv_path.exists():
            logger.info(f"Creating virtual environment at {venv_path}")
            self._run_command([sys.executable, "-m", "venv", str(venv_path)])

        return venv_path

    def _adjust_extras_for_hardware(self, extras: Optional[List[str]]) -> List[str]:
        """
        Adjust extras based on detected hardware.
        Replaces generic 'asr' and 'all' with hardware-specific ASR packages.
        """
        if not extras:
            return []
        
        # Detect hardware
        try:
            sys.path.insert(0, str(self.root_dir))
            from nabcommon.hardware_detect import can_use_vosk, detect_pi_model

            pi_model = detect_pi_model()
            use_vosk = can_use_vosk()

            if pi_model:
                logger.info(f"Detected hardware: {pi_model}")
            else:
                logger.info("Could not detect Pi model, defaulting to Kaldi ASR")
                use_vosk = False

        except Exception as e:
            logger.warning(f"Hardware detection failed: {e}")
            logger.info("Defaulting to Kaldi ASR")
            use_vosk = False
        
        adjusted = []
        for extra in extras:
            if extra == "asr":
                # Replace generic 'asr' with hardware-specific variant
                if use_vosk:
                    logger.info("Using Vosk ASR (recommended for Pi Zero 2 W)")
                    adjusted.append("asr-vosk")
                else:
                    logger.info("Using Kaldi ASR (for Pi Zero W)")
                    adjusted.append("asr-kaldi")
            elif extra == "all":
                # Expand 'all' to include hardware-specific ASR
                adjusted.extend(["hardware", "services"])
                if use_vosk:
                    adjusted.append("asr-vosk")
                else:
                    adjusted.append("asr-kaldi")
                adjusted.append("nlu")
            else:
                adjusted.append(extra)
        
        return adjusted

    def _install_system_dependencies(self, extras: List[str]):
        """Install required system packages via apt-get."""
        system_packages = []
        
        # Padatious requires libfann and SWIG for fann2 build
        if "nlu" in extras:
            system_packages.extend(["libfann-dev", "swig"])
        
        # Hardware support may need additional packages
        if "hardware" in extras:
            system_packages.extend(["portaudio19-dev", "python3-pyaudio"])
        
        if not system_packages:
            return
        
        logger.info(f"Installing system dependencies: {', '.join(system_packages)}")
        logger.info("This requires sudo privileges...")
        
        try:
            # Check if packages are already installed
            missing_packages = []
            for pkg in system_packages:
                result = subprocess.run(
                    ["dpkg", "-l", pkg],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode != 0:
                    missing_packages.append(pkg)
            
            if not missing_packages:
                logger.info("All system dependencies already installed")
                return
            
            # Update package lists
            logger.info("Updating package lists...")
            self._run_command(["sudo", "apt-get", "update", "-qq"])
            
            # Install missing packages
            logger.info(f"Installing: {', '.join(missing_packages)}")
            self._run_command(
                ["sudo", "apt-get", "install", "-y"] + missing_packages
            )
            
            logger.info("✓ System dependencies installed")
            
        except Exception as e:
            logger.warning(f"Failed to install system dependencies: {e}")
            logger.warning("You may need to install them manually:")
            logger.warning(f"  sudo apt-get install {' '.join(system_packages)}")
            if not self.interactive or not self._confirm("Continue anyway?"):
                raise InstallationError("System dependencies installation failed")

    def install_python_packages(
        self, venv_path: Path, extras: Optional[List[str]] = None
    ):
        """Install Python packages using pip."""
        pip = venv_path / "bin" / "pip"

        # Upgrade pip and install wheel
        logger.info("Upgrading pip and installing wheel")
        self._run_command([str(pip), "install", "--upgrade", "pip", "wheel"])

        # Detect hardware to adjust ASR dependencies
        major, minor = sys.version_info[:2]
        adjusted_extras = self._adjust_extras_for_hardware(extras)
        
        # Install system dependencies if needed
        self._install_system_dependencies(adjusted_extras)
        
        # For NLU with Padatious, install fann2 separately first with proper build env
        build_env = os.environ.copy()
        if adjusted_extras and "nlu" in adjusted_extras:
            logger.info("Pre-installing fann2 for Padatious (requires SWIG)...")
            # Install SWIG which is needed to build fann2
            try:
                result = subprocess.run(
                    ["dpkg", "-l", "swig"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode != 0:
                    logger.info("Installing SWIG for fann2 build...")
                    self._run_command(["sudo", "apt-get", "install", "-y", "swig"])
            except Exception as e:
                logger.warning(f"Could not install SWIG: {e}")
            
            # Try to install fann2 from pre-built wheel or build with proper env
            build_env["CFLAGS"] = build_env.get("CFLAGS", "") + " -I/usr/include"
            build_env["LDFLAGS"] = build_env.get("LDFLAGS", "") + " -L/usr/lib/aarch64-linux-gnu"
            try:
                logger.info("Installing fann2...")
                self._run_command(
                    [str(pip), "install", "fann2==1.1.2"],
                    env=build_env,
                    check=False  # Don't fail if this doesn't work
                )
            except Exception as e:
                logger.warning(f"fann2 pre-installation failed, will retry with padatious: {e}")
        
        # For Kaldi ASR (Pi Zero W only with Python 3.7-3.9), install build dependencies
        if adjusted_extras and "asr-kaldi" in adjusted_extras:
            if major == 3 and minor >= 11:
                logger.error(
                    f"Python {major}.{minor} is not compatible with Kaldi ASR (requires numpy 1.21.4)."
                )
                logger.error(
                    "On Pi Zero 2 W, please use Vosk ASR which is automatically selected."
                )
                logger.error(
                    "On Pi Zero W, please use Python 3.9 or earlier for Kaldi ASR support."
                )
                raise InstallationError(
                    "Python 3.11+ requires Vosk ASR (Pi Zero 2 W or better)"
                )
            
            logger.info("Installing build dependencies for Kaldi ASR...")
            self._run_command(
                [str(pip), "install", "Cython==0.29.30", "numpy==1.21.4"]
            )

        # Install package with optional extras (using adjusted extras)
        install_cmd = [str(pip), "install", "-e", str(self.root_dir)]

        if adjusted_extras:
            extras_str = ",".join(adjusted_extras)
            install_cmd[-1] = f"{self.root_dir}[{extras_str}]"

        logger.info(f"Installing Pynab with extras: {adjusted_extras or ['none']}")
        self._run_command(install_cmd, env=build_env)

        # Post-installation: Download models for ASR/NLU if needed
        if adjusted_extras and ("asr-vosk" in adjusted_extras or "asr-kaldi" in adjusted_extras or "nlu" in adjusted_extras):
            self.install_asr_nlu_models(venv_path, adjusted_extras)

    def install_asr_nlu_models(self, venv_path: Path, extras: List[str]):
        """
        Install ASR and NLU models based on installed packages.
        This replaces the old Kaldi/Snips model download and training.
        """
        logger.info("\n" + "=" * 60)
        logger.info("Installing ASR/NLU models")
        logger.info("=" * 60)

        # Install ASR models based on which variant was installed
        if "asr-vosk" in extras:
            self._install_vosk_models()
        elif "asr-kaldi" in extras:
            self._install_kaldi_models()

        # NLU is now Padatious - no models to download!
        if "nlu" in extras:
            logger.info("NLU: Using Padatious (no model download needed)")
            logger.info(
                "Intent files will be loaded from service directories at runtime"
            )

    def _install_vosk_models(self):
        """Install Vosk models for Pi Zero 2 W and better."""
        import urllib.request
        import zipfile

        logger.info("Installing Vosk ASR models...")

        models_dir = Path("/opt/vosk/models")
        models_dir.mkdir(parents=True, exist_ok=True)

        # Ask user which language(s) to install
        if self.interactive:
            print("\nVosk model installation:")
            print("For optimal memory usage on Pi Zero 2 W (512MB RAM),")
            print("it's recommended to install only ONE language model.")
            install_fr = input("Install French model (41MB)? [Y/n]: ").strip().lower() not in ["n", "no"]
            install_en = input("Install English model (40MB)? [y/N]: ").strip().lower() in ["y", "yes"]
        else:
            # Non-interactive: install French by default
            install_fr = True
            install_en = False

        models = []
        if install_fr:
            models.append(
                {
                    "name": "vosk-model-small-fr-0.22",
                    "url": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
                    "size": "41MB",
                }
            )
        if install_en:
            models.append(
                {
                    "name": "vosk-model-small-en-us-0.15",
                    "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
                    "size": "40MB",
                }
            )

        for model in models:
            model_path = models_dir / model["name"]
            if model_path.exists():
                logger.info(f"Model {model['name']} already exists, skipping")
                continue

            logger.info(f"Downloading {model['name']} ({model['size']})...")
            zip_path = models_dir / f"{model['name']}.zip"

            try:
                urllib.request.urlretrieve(model["url"], zip_path)
                logger.info(f"Extracting {model['name']}...")
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(models_dir)
                zip_path.unlink()
                logger.info(f"✓ Installed {model['name']}")
            except Exception as e:
                logger.error(f"Failed to install {model['name']}: {e}")

        # Optional: Configure ZRAM for better memory management
        if self.interactive:
            response = input(
                "\nConfigure ZRAM swap for better memory management (recommended for Pi Zero 2 W)? [y/N]: "
            ).strip().lower()
            if response in ["y", "yes"]:
                self._setup_zram()

    def _install_kaldi_models(self):
        """Install Kaldi models for Pi Zero W (legacy)."""
        logger.info("Installing Kaldi ASR models...")
        logger.info(
            "Note: Kaldi installation requires running the legacy install.sh script"
        )
        logger.info("or manual installation of Kaldi binaries to /opt/kaldi/")

        # For now, just inform the user
        # The full Kaldi installation logic is complex and lives in install.sh
        logger.warning(
            "Kaldi ASR installation is complex and requires system-level changes.\n"
            "Please refer to INSTALL.md or run the legacy install.sh script."
        )

    def _setup_zram(self):
        """Setup ZRAM swap for better memory management on Pi Zero 2 W."""
        logger.info("Setting up ZRAM swap...")

        try:
            # Check if zram-tools is installed
            result = subprocess.run(
                ["dpkg", "-l", "zram-tools"], capture_output=True, text=True
            )

            if result.returncode != 0:
                logger.info("Installing zram-tools...")
                self._run_command(["sudo", "apt-get", "update"])
                self._run_command(["sudo", "apt-get", "install", "-y", "zram-tools"])

            logger.info("✓ ZRAM configured")
            logger.info("Note: Reboot required for ZRAM to take effect")

        except Exception as e:
            logger.warning(f"Failed to setup ZRAM: {e}")
            logger.info(
                "You can manually install it later with: sudo apt-get install zram-tools"
            )

    def select_installation_profile(self) -> List[str]:
        """Let user select which components to install."""
        if not self.interactive:
            logger.info("Non-interactive mode: using 'all' profile")
            return ["all"]

        print("\nSelect installation profile:")
        print("1. Minimal (core only, no hardware/ASR/NLU)")
        print("2. Hardware (core + Raspberry Pi hardware support)")
        print("3. Full (all components including ASR and NLU)")
        print("4. Custom (select individual components)")
        print("5. Development (full + dev tools)")

        choice = input("\nEnter choice [1-5, default=3]: ").strip() or "3"

        profiles = {
            "1": [],
            "2": ["hardware"],
            "3": ["all"],
            "4": self._select_custom_components(),
            "5": ["all", "dev"],
        }

        return profiles.get(choice, ["all"])

    def _select_custom_components(self) -> List[str]:
        """Let user select individual components."""
        components = {
            "hardware": "Raspberry Pi hardware support (GPIO, LEDs, sound)",
            "asr": "Automatic Speech Recognition (Vosk for Pi Zero 2 W, Kaldi for Pi Zero W)",
            "nlu": "Natural Language Understanding (Padatious)",
            "services": "External services (Mastodon, weather)",
            "dev": "Development and testing tools",
        }

        selected = []
        print("\nAvailable components:")
        for key, desc in components.items():
            if self._confirm(f"Install {key} ({desc})?"):
                selected.append(key)

        return selected

    def install(
        self, venv_path: Optional[Path] = None, extras: Optional[List[str]] = None
    ):
        """Run the installation process."""
        logger.info("Starting Pynab installation")

        # Platform checks
        if not self.check_python_version():
            raise InstallationError("Python version check failed")

        if not self.check_platform():
            if not self._confirm("Continue with installation despite warnings?"):
                logger.info("Installation cancelled by user")
                return

        # Select installation profile
        if extras is None:
            extras = self.select_installation_profile()

        # Setup virtual environment
        if venv_path is None:
            venv_path = self.root_dir / "venv"

        venv_path = self.setup_venv(venv_path)

        # Install Python packages
        self.install_python_packages(venv_path, extras)

        logger.info("\n" + "=" * 60)
        logger.info("Python packages installation completed!")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Activate the virtual environment:")
        logger.info(f"   source {venv_path}/bin/activate")
        logger.info("\n2. For full system setup (database, services, drivers), run:")
        logger.info("   python -m scripts.setup_system")
        logger.info("\n3. For hardware driver installation (Raspberry Pi only):")
        logger.info("   sudo python -m scripts.setup_drivers")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Modern modular installer for Pynab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive installation (recommended for first-time users)
  python -m scripts.install

  # Non-interactive full installation
  python -m scripts.install --non-interactive --profile all

  # Install only hardware support
  python -m scripts.install --extras hardware

  # Install with custom virtual environment location
  python -m scripts.install --venv /opt/pynab/venv
        """,
    )

    parser.add_argument(
        "--venv", type=Path, help="Path to virtual environment (default: ./venv)"
    )

    parser.add_argument(
        "--extras",
        nargs="+",
        choices=["hardware", "asr", "nlu", "services", "dev", "all"],
        help="Additional components to install",
    )

    parser.add_argument(
        "--profile",
        choices=["minimal", "hardware", "full", "dev"],
        help="Installation profile (full=all, dev=all+dev)",
    )

    parser.add_argument(
        "--non-interactive", action="store_true", help="Run in non-interactive mode"
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine root directory
    root_dir = Path(__file__).parent.parent.resolve()

    # Map profile to extras
    if args.profile:
        profile_map = {
            "minimal": [],
            "hardware": ["hardware"],
            "full": ["all"],
            "dev": ["all", "dev"],
        }
        extras = profile_map[args.profile]
    else:
        extras = args.extras

    try:
        installer = PynabInstaller(
            root_dir=root_dir, interactive=not args.non_interactive
        )
        installer.install(venv_path=args.venv, extras=extras)
    except InstallationError as e:
        logger.error(f"Installation failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nInstallation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
