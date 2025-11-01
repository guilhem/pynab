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
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
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
        if self.system != 'Linux':
            logger.warning(f"Platform {self.system} may not be fully supported")
            return False
            
        # Check if Raspberry Pi
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
                if 'Raspberry Pi' not in cpuinfo:
                    logger.warning("This installation is optimized for Raspberry Pi")
                    return self.interactive and self._confirm("Continue anyway?")
        except FileNotFoundError:
            logger.warning("Cannot detect hardware platform")
            
        return True
    
    def check_python_version(self) -> bool:
        """Check if Python version is supported."""
        major, minor = sys.version_info[:2]
        if major < 3 or (major == 3 and minor < 7):
            logger.error(f"Python {major}.{minor} is not supported. Requires Python 3.7+")
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
        return response in ['y', 'yes']
    
    def _run_command(self, cmd: List[str], check: bool = True, 
                     capture_output: bool = False) -> subprocess.CompletedProcess:
        """Run a command with error handling."""
        logger.info(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, 
                check=check,
                capture_output=capture_output,
                text=True
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
                with open(pyvenv_cfg, 'r') as f:
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
    
    def install_python_packages(self, venv_path: Path, 
                                extras: Optional[List[str]] = None):
        """Install Python packages using pip."""
        pip = venv_path / "bin" / "pip"
        
        # Upgrade pip and install wheel
        logger.info("Upgrading pip and installing wheel")
        self._run_command([str(pip), "install", "--upgrade", "pip", "wheel"])
        
        # Install package with optional extras
        install_cmd = [str(pip), "install", "-e", str(self.root_dir)]
        
        if extras:
            extras_str = ",".join(extras)
            install_cmd[-1] = f"{self.root_dir}[{extras_str}]"
        
        logger.info(f"Installing Pynab with extras: {extras or ['none']}")
        self._run_command(install_cmd)
    
    def select_installation_profile(self) -> List[str]:
        """Let user select which components to install."""
        if not self.interactive:
            logger.info("Non-interactive mode: using 'all' profile")
            return ['all']
        
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
            "5": ["all", "dev"]
        }
        
        return profiles.get(choice, ["all"])
    
    def _select_custom_components(self) -> List[str]:
        """Let user select individual components."""
        components = {
            "hardware": "Raspberry Pi hardware support (GPIO, LEDs, sound)",
            "asr": "Automatic Speech Recognition (Kaldi)",
            "nlu": "Natural Language Understanding (Snips)",
            "services": "External services (Mastodon, weather)",
            "dev": "Development and testing tools"
        }
        
        selected = []
        print("\nAvailable components:")
        for key, desc in components.items():
            if self._confirm(f"Install {key} ({desc})?"):
                selected.append(key)
        
        return selected
    
    def install(self, venv_path: Optional[Path] = None, 
                extras: Optional[List[str]] = None):
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
        
        logger.info("\n" + "="*60)
        logger.info("Python packages installation completed!")
        logger.info("="*60)
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
        """
    )
    
    parser.add_argument(
        "--venv",
        type=Path,
        help="Path to virtual environment (default: ./venv)"
    )
    
    parser.add_argument(
        "--extras",
        nargs="+",
        choices=["hardware", "asr", "nlu", "services", "dev", "all"],
        help="Additional components to install"
    )
    
    parser.add_argument(
        "--profile",
        choices=["minimal", "hardware", "full", "dev"],
        help="Installation profile (full=all, dev=all+dev)"
    )
    
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run in non-interactive mode"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
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
            "dev": ["all", "dev"]
        }
        extras = profile_map[args.profile]
    else:
        extras = args.extras
    
    try:
        installer = PynabInstaller(
            root_dir=root_dir,
            interactive=not args.non_interactive
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
