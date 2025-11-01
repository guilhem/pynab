#!/usr/bin/env python3
"""
Hardware drivers setup for Pynab.

This script handles installation and configuration of:
- Sound card drivers (WM8960 for Ulule 2019 cards, HiFiBerry for Maker Faire 2018)
- Ears driver (tagtagtag-ears)
- RFID/NFC drivers (CR14, ST25R391x)

Must be run with sudo for driver installation.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DriverInstallationError(Exception):
    """Exception raised for driver installation errors."""
    pass


class HardwareDetector:
    """Detect hardware configuration."""
    
    @staticmethod
    def is_raspberry_pi() -> bool:
        """Check if running on Raspberry Pi."""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                return 'Raspberry Pi' in f.read()
        except FileNotFoundError:
            return False
    
    @staticmethod
    def is_pi_zero() -> bool:
        """Check if running on Raspberry Pi Zero."""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()
                return 'Raspberry Pi Zero' in content
        except FileNotFoundError:
            return False
    
    @staticmethod
    def detect_sound_card() -> Optional[str]:
        """Detect installed sound card."""
        try:
            result = subprocess.run(
                ['aplay', '-L'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                if 'tagtagtagsound' in result.stdout:
                    return 'wm8960'
                elif 'hifiberry' in result.stdout:
                    return 'hifiberry'
        except FileNotFoundError:
            pass
        return None
    
    @staticmethod
    def has_ears_driver() -> bool:
        """Check if ears driver is installed."""
        return os.path.exists('/dev/ear0')
    
    @staticmethod
    def has_rfid_driver() -> bool:
        """Check if RFID/NFC driver is installed."""
        return os.path.exists('/dev/rfid0') or os.path.exists('/dev/nfc0')


class DriverInstaller:
    """Handle driver installation and updates."""
    
    def __init__(self, inst_dir: Path, upgrade: bool = False):
        self.inst_dir = inst_dir
        self.upgrade = upgrade
        self.reboot_required = False
        
    def _run_command(self, cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
        """Run a command with error handling."""
        logger.info(f"Running: {' '.join(cmd)}")
        try:
            return subprocess.run(cmd, check=True, **kwargs)
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}")
            raise DriverInstallationError(f"Command failed: {' '.join(cmd)}")
    
    def _build_and_install_driver(self, driver_dir: Path):
        """Build and install a kernel driver for all installed kernels."""
        logger.info(f"Building driver in {driver_dir}")
        
        kernel_dirs = list(Path('/lib/modules').glob('*/build'))
        if not kernel_dirs:
            raise DriverInstallationError("No kernel build directories found")
        
        for kernel_build_dir in kernel_dirs:
            kernel = kernel_build_dir.parent.name
            logger.info(f"Building for kernel {kernel}")
            
            # Build
            self._run_command(
                ['make', f'KERNELRELEASE={kernel}'],
                cwd=driver_dir
            )
            
            # Install
            self._run_command(
                ['sudo', 'make', 'install', f'KERNELRELEASE={kernel}'],
                cwd=driver_dir
            )
            
            # Clean
            self._run_command(
                ['make', 'clean', f'KERNELRELEASE={kernel}'],
                cwd=driver_dir
            )
    
    def _git_clone_or_update(self, repo_url: str, target_dir: Path, 
                            branch: str = 'master') -> bool:
        """Clone or update a git repository. Returns True if changes were made."""
        if target_dir.exists():
            if not self.upgrade:
                logger.info(f"{target_dir} already exists, skipping")
                return False
            
            logger.info(f"Updating {target_dir}")
            result = self._run_command(
                ['git', 'pull'],
                cwd=target_dir,
                capture_output=True,
                text=True
            )
            return "Already up to date." not in result.stdout
        else:
            logger.info(f"Cloning {repo_url} to {target_dir}")
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            self._run_command([
                'git', 'clone', '--depth', '1', '-b', branch,
                repo_url, str(target_dir)
            ])
            return True
    
    def install_sound_driver(self, sound_card: Optional[str] = None) -> bool:
        """Install sound card driver. Returns True if reboot required."""
        if sound_card == 'hifiberry':
            logger.info("HiFiBerry detected (Maker Faire 2018), no WM8960 installation needed")
            return False
        
        driver_dir = self.inst_dir / 'wm8960'
        changed = self._git_clone_or_update(
            'https://github.com/pguyot/wm8960',
            driver_dir,
            branch='tagtagtag-sound'
        )
        
        if changed or not self.upgrade:
            self._build_and_install_driver(driver_dir)
            return True
        
        return False
    
    def install_ears_driver(self) -> bool:
        """Install ears driver. Returns True if reboot required."""
        driver_dir = self.inst_dir / 'tagtagtag-ears'
        changed = self._git_clone_or_update(
            'https://github.com/pguyot/tagtagtag-ears',
            driver_dir,
            branch='master'
        )
        
        if changed or not driver_dir.exists():
            self._build_and_install_driver(driver_dir)
            return True
        
        return False
    
    def install_rfid_drivers(self) -> bool:
        """Install RFID/NFC drivers. Returns True if reboot required."""
        reboot = False
        
        # CR14 driver (old RFID reader)
        cr14_dir = self.inst_dir / 'cr14'
        changed = self._git_clone_or_update(
            'https://github.com/pguyot/cr14',
            cr14_dir,
            branch='master'
        )
        
        if changed or not cr14_dir.exists():
            self._build_and_install_driver(cr14_dir)
            reboot = True
        
        # ST25R391x driver (2022 NFC card)
        st25_dir = self.inst_dir / 'st25r391x'
        changed = self._git_clone_or_update(
            'https://github.com/pguyot/st25r391x',
            st25_dir,
            branch='main'
        )
        
        if changed or not st25_dir.exists():
            self._build_and_install_driver(st25_dir)
            
            # Disable ST25R391x by default (conflicts with CR14, nabboot will switch)
            config_path = Path('/boot/config.txt')
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = f.read()
                
                if 'dtoverlay=st25r391x' in config and not config.count('#dtoverlay=st25r391x'):
                    logger.info("Disabling ST25R391x driver in /boot/config.txt")
                    self._run_command([
                        'sudo', 'sed', '-i',
                        's/^dtoverlay=st25r391x/#dtoverlay=st25r391x/',
                        str(config_path)
                    ])
            
            # Enable i2c-dev
            modules_path = Path('/etc/modules')
            if modules_path.exists():
                with open(modules_path, 'r') as f:
                    modules = f.read()
                
                if 'i2c-dev' not in modules:
                    logger.info("Enabling i2c-dev in /etc/modules")
                    with open(modules_path, 'a') as f:
                        f.write('\ni2c-dev\n')
            
            reboot = True
        
        return reboot


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Install hardware drivers for Pynab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script must be run with sudo privileges.

Examples:
  # Install all drivers
  sudo python -m scripts.setup_drivers
  
  # Upgrade existing drivers
  sudo python -m scripts.setup_drivers --upgrade
  
  # Install only specific drivers
  sudo python -m scripts.setup_drivers --sound --ears
  
  # Dry run to see what would be installed
  sudo python -m scripts.setup_drivers --dry-run
        """
    )
    
    parser.add_argument(
        '--upgrade',
        action='store_true',
        help='Upgrade existing drivers'
    )
    
    parser.add_argument(
        '--inst-dir',
        type=Path,
        default=Path('/opt'),
        help='Installation directory for drivers (default: /opt)'
    )
    
    parser.add_argument(
        '--sound',
        action='store_true',
        help='Install only sound driver'
    )
    
    parser.add_argument(
        '--ears',
        action='store_true',
        help='Install only ears driver'
    )
    
    parser.add_argument(
        '--rfid',
        action='store_true',
        help='Install only RFID/NFC drivers'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check if running as root
    if os.geteuid() != 0 and not args.dry_run:
        logger.error("This script must be run as root (use sudo)")
        sys.exit(1)
    
    # Check platform
    detector = HardwareDetector()
    if not detector.is_raspberry_pi():
        logger.error("This script is only for Raspberry Pi")
        sys.exit(1)
    
    if detector.is_pi_zero():
        logger.info("Raspberry Pi Zero detected")
    else:
        logger.warning("Not a Pi Zero - installation may work but is not officially supported")
    
    # Detect current hardware
    logger.info("Detecting hardware configuration...")
    sound_card = detector.detect_sound_card()
    has_ears = detector.has_ears_driver()
    has_rfid = detector.has_rfid_driver()
    
    logger.info(f"Sound card: {sound_card or 'Not detected'}")
    logger.info(f"Ears driver: {'Installed' if has_ears else 'Not installed'}")
    logger.info(f"RFID driver: {'Installed' if has_rfid else 'Not installed'}")
    
    if args.dry_run:
        logger.info("\n=== DRY RUN MODE ===")
        logger.info("Would install/update drivers based on hardware detection")
        return
    
    # Determine what to install
    install_all = not (args.sound or args.ears or args.rfid)
    
    try:
        installer = DriverInstaller(args.inst_dir, args.upgrade)
        reboot_required = False
        
        if install_all or args.sound:
            logger.info("\n=== Installing sound driver ===")
            if installer.install_sound_driver(sound_card):
                reboot_required = True
        
        if install_all or args.ears:
            logger.info("\n=== Installing ears driver ===")
            if installer.install_ears_driver():
                reboot_required = True
        
        if install_all or args.rfid:
            logger.info("\n=== Installing RFID/NFC drivers ===")
            if installer.install_rfid_drivers():
                reboot_required = True
        
        logger.info("\n" + "="*60)
        logger.info("Driver installation completed!")
        logger.info("="*60)
        
        if reboot_required:
            logger.warning("\n⚠️  REBOOT REQUIRED for drivers to take effect")
            logger.info("Run: sudo reboot")
        else:
            logger.info("\nNo reboot required")
        
    except DriverInstallationError as e:
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
