#!/usr/bin/env python3
"""
Dashboard For Export Configuration Script
========================================

Interactive setup script for Dashboard For Export.py

This script helps configure:
- Calendar feed URLs (up to 5)
- Local output directory path
- Basic settings for the dashboard system

Created: July 18, 2025
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
import re

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

class DashboardConfigurator:
    """Interactive configuration manager for Dashboard For Export."""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.env_file = self.base_dir / '.env'
        self.calendar_feeds_file = self.base_dir / 'calendar_feeds.txt'
        self.config = {}
        
    def run(self):
        """Run the interactive configuration setup."""
        print("=" * 60)
        print("🚀 Dashboard For Export Configuration Setup")
        print("=" * 60)
        print()
        
        try:
            # Load existing configuration
            self._load_existing_config()
            
            # Show menu
            self._show_menu()
            
            # Get user choice
            choice = self._get_user_choice()
            
            # Process choice
            self._process_choice(choice)
            
        except KeyboardInterrupt:
            print("\n\n❌ Configuration cancelled by user.")
            sys.exit(1)
        except Exception as e:
            logging.error(f"❌ Configuration failed: {e}")
            sys.exit(1)
    
    def _load_existing_config(self):
        """Load existing configuration from .env file."""
        if self.env_file.exists():
            print("📋 Loading existing configuration...")
            try:
                with open(self.env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            self.config[key.strip()] = value.strip().strip('"\'')
                logging.info(f"✅ Loaded {len(self.config)} existing configuration items")
            except Exception as e:
                logging.warning(f"⚠️ Could not load existing .env file: {e}")
        else:
            print("📋 No existing configuration found. Starting fresh.")
    
    def _show_menu(self):
        """Display the configuration menu."""
        print("🔧 Configuration Options:")
        print()
        print("1. Configure ALL settings (comprehensive setup)")
        print("2. Configure ONLY calendar feed URLs")
        print("3. Configure all EXCEPT emoji and weather API preferences")
        print("4. Quick setup (essentials only)")
        print("5. Skip configuration (keep current settings)")
        print("6. Configure ONLY local output directory path")
        print("7. Exit without changes")
        print()
    
    def _get_user_choice(self) -> int:
        """Get and validate user menu choice."""
        while True:
            try:
                choice = input("👆 Enter your choice (1-7): ").strip()
                choice_num = int(choice)
                if 1 <= choice_num <= 7:
                    return choice_num
                else:
                    print("❌ Please enter a number between 1 and 7.")
            except ValueError:
                print("❌ Please enter a valid number.")
    
    def _process_choice(self, choice: int):
        """Process the user's menu choice."""
        print()
        
        if choice == 1:
            self._configure_all()
        elif choice == 2:
            self._configure_calendar_feeds_only()
        elif choice == 3:
            self._configure_all_except_emoji_weather()
        elif choice == 4:
            self._configure_essentials()
        elif choice == 5:
            print("⏭️ Skipping configuration. Current settings preserved.")
            return
        elif choice == 6:
            self._configure_output_directory_only()
        elif choice == 7:
            print("👋 Exiting without changes.")
            sys.exit(0)
        
        # Save configuration
        self._save_configuration()
        print()
        print("✅ Configuration completed successfully!")
        print(f"📁 Configuration saved to: {self.env_file}")
        print(f"📅 Calendar feeds saved to: {self.calendar_feeds_file}")
        print()
        print("🚀 You can now run: python \"Dashboard For Export.py\"")
    
    def _configure_all(self):
        """Configure all available settings."""
        print("🔧 Configuring ALL settings...")
        print()
        
        self._configure_remarkable_settings()
        self._configure_calendar_feeds()
        self._configure_location_settings()
        self._configure_output_settings()
        self._configure_task_lists()
        self._configure_display_settings()
    
    def _configure_calendar_feeds_only(self):
        """Configure only calendar feed URLs."""
        print("📅 Configuring calendar feeds only...")
        print()
        self._configure_calendar_feeds()
    
    def _configure_all_except_emoji_weather(self):
        """Configure all except emoji and weather API preferences."""
        print("🔧 Configuring all settings except emoji and weather API...")
        print()
        
        self._configure_remarkable_settings()
        self._configure_calendar_feeds()
        self._configure_output_settings()
        self._configure_task_lists()
        self._configure_display_settings()
    
    def _configure_essentials(self):
        """Configure essential settings only."""
        print("⚡ Quick setup - essentials only...")
        print()
        
        self._configure_remarkable_settings()
        self._configure_calendar_feeds()
        self._configure_output_settings()
        
        # Ask about cover image in essentials
        print("📸 Cover Image (Optional)")
        print("-" * 25)
        
        current_cover = self.config.get('COVER_IMAGE_PATH', 'cover-image.jpg')
        print(f"Current cover image: {current_cover}")
        
        setup_cover = input("Set up cover image? (y/n, default: n): ").strip().lower()
        if setup_cover == 'y':
            new_cover = input("Enter cover image path (JPG/PNG): ").strip()
            if new_cover:
                cover_path = Path(new_cover)
                if not cover_path.is_absolute():
                    cover_path = self.base_dir / cover_path
                
                self.config['COVER_IMAGE_PATH'] = str(cover_path)
                if cover_path.exists():
                    print(f"✅ Cover image set to: {cover_path}")
                else:
                    print("⚠️ Cover image file not found. Setting anyway (add file later).")
        
        print()
    
    def _configure_output_directory_only(self):
        """Configure only the local output directory path."""
        print("📁 Configuring local output directory only...")
        print()
        self._configure_output_settings()
    
    def _configure_remarkable_settings(self):
        """Configure reMarkable device settings."""
        print("📱 reMarkable Device Settings")
        print("-" * 30)
        
        # WiFi IP Address
        current_ip = self.config.get('REMARKABLE_IP', '192.168.1.100')
        print(f"Current reMarkable IP: {current_ip}")
        
        new_ip = input("Enter reMarkable WiFi IP address (or press Enter to keep current): ").strip()
        if new_ip:
            if self._validate_ip_address(new_ip):
                self.config['REMARKABLE_IP'] = new_ip
            else:
                print("❌ Invalid IP address format. Please enter a valid IP (e.g., 192.168.1.100)")
                self.config['REMARKABLE_IP'] = current_ip  # Keep current value
        else:
            self.config['REMARKABLE_IP'] = current_ip  # Always save current value
        
        # SSH Key Path
        current_key = self.config.get('REMARKABLE_SSH_KEY', str(Path.home() / '.ssh' / 'id_rsa'))
        print(f"Current SSH key path: {current_key}")
        
        new_key = input("Enter SSH key path (or press Enter to keep current): ").strip()
        if new_key:
            if Path(new_key).exists():
                self.config['REMARKABLE_SSH_KEY'] = new_key
            else:
                print("⚠️ SSH key file not found. Setting anyway (you can create it later).")
                self.config['REMARKABLE_SSH_KEY'] = new_key
        else:
            self.config['REMARKABLE_SSH_KEY'] = current_key  # Always save current value
        
        print()
    
    def _configure_calendar_feeds(self):
        """Configure calendar feed URLs."""
        print("📅 Calendar Feed URLs")
        print("-" * 20)
        print("Enter up to 5 calendar feed URLs (iCal format).")
        print("Press Enter with empty input to finish.")
        print()
        
        # Load existing feeds
        existing_feeds = []
        if self.calendar_feeds_file.exists():
            try:
                with open(self.calendar_feeds_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            existing_feeds.append(line)
            except Exception as e:
                logging.warning(f"Could not load existing calendar feeds: {e}")
        
        # Show existing feeds
        if existing_feeds:
            print("Current calendar feeds:")
            for i, feed in enumerate(existing_feeds, 1):
                print(f"  {i}. {feed}")
            print()
        
        # Get new feeds
        feeds = []
        for i in range(5):
            while True:
                prompt = f"Calendar feed {i+1} URL (or press Enter to finish): "
                url = input(prompt).strip()
                
                if not url:
                    break
                
                if self._validate_calendar_url(url):
                    feeds.append(url)
                    print(f"✅ Added: {url}")
                    break
                else:
                    print("❌ Invalid URL format. Please enter a valid calendar URL.")
        
        # Save feeds to file
        if feeds:
            self._save_calendar_feeds(feeds)
        elif existing_feeds:
            print("⏭️ Keeping existing calendar feeds.")
        else:
            print("⚠️ No calendar feeds configured. Dashboard will show no events.")
        
        print()
    
    def _configure_location_settings(self):
        """Configure location and weather settings."""
        print("📍 Location & Weather Settings")
        print("-" * 30)
        
        # Home coordinates
        current_home_lat = self.config.get('HOME_LAT', '1.29')
        current_home_lon = self.config.get('HOME_LON', '103.85')
        
        print(f"Current home coordinates: {current_home_lat}, {current_home_lon}")
        print("(Default: Singapore)")
        
        new_lat = input("Enter home latitude (or press Enter to keep current): ").strip()
        if new_lat:
            try:
                float(new_lat)
                self.config['HOME_LAT'] = new_lat
            except ValueError:
                print("❌ Invalid latitude. Keeping current value.")
                self.config['HOME_LAT'] = current_home_lat
        else:
            self.config['HOME_LAT'] = current_home_lat  # Always save current value
        
        new_lon = input("Enter home longitude (or press Enter to keep current): ").strip()
        if new_lon:
            try:
                float(new_lon)
                self.config['HOME_LON'] = new_lon
            except ValueError:
                print("❌ Invalid longitude. Keeping current value.")
                self.config['HOME_LON'] = current_home_lon
        else:
            self.config['HOME_LON'] = current_home_lon  # Always save current value
        
        # Work coordinates
        current_work_lat = self.config.get('WORK_LAT', '1.29')
        current_work_lon = self.config.get('WORK_LON', '103.85')
        
        print(f"Current work coordinates: {current_work_lat}, {current_work_lon}")
        
        new_work_lat = input("Enter work latitude (or press Enter to keep current): ").strip()
        if new_work_lat:
            try:
                float(new_work_lat)
                self.config['WORK_LAT'] = new_work_lat
            except ValueError:
                print("❌ Invalid latitude. Keeping current value.")
                self.config['WORK_LAT'] = current_work_lat
        else:
            self.config['WORK_LAT'] = current_work_lat  # Always save current value
        
        new_work_lon = input("Enter work longitude (or press Enter to keep current): ").strip()
        if new_work_lon:
            try:
                float(new_work_lon)
                self.config['WORK_LON'] = new_work_lon
            except ValueError:
                print("❌ Invalid longitude. Keeping current value.")
                self.config['WORK_LON'] = current_work_lon
        else:
            self.config['WORK_LON'] = current_work_lon  # Always save current value
        
        print()
    
    def _configure_output_settings(self):
        """Configure output directory settings."""
        print("📁 Output Settings")
        print("-" * 17)
        
        # Local output directory - use generic user-based path
        default_output = f"C:/Users/{os.getenv('USERNAME', 'User')}/Documents/Dashboard_Output"
        current_output = self.config.get('LOCAL_OUTPUT_PATH', default_output)
        print(f"Current output directory: {current_output}")
        
        new_output = input("Enter local output directory path (or press Enter to keep current): ").strip()
        if new_output:
            output_path = Path(new_output)
            try:
                # Try to create directory to test permissions
                output_path.mkdir(parents=True, exist_ok=True)
                self.config['LOCAL_OUTPUT_PATH'] = str(output_path)
                print(f"✅ Output directory set to: {output_path}")
            except Exception as e:
                print(f"❌ Could not create directory: {e}")
                print("⚠️ Setting anyway (you can create it manually later).")
                self.config['LOCAL_OUTPUT_PATH'] = str(output_path)
        else:
            self.config['LOCAL_OUTPUT_PATH'] = current_output  # Always save current value
        
        print()
    
    def _configure_task_lists(self):
        """Configure task lists for today and tomorrow."""
        print("📋 Task Lists Configuration")
        print("-" * 26)
        print("Configure your daily task checklists.")
        print()
        
        # Today's tasks
        print("Today's Task List:")
        today_tasks = [
            "Top 3 Things",
            "Devotions, SFAD, Journal",
            "Meals & Expenses",
            "Pegboard Compline"
        ]
        
        print("Current today's tasks:")
        for i, task in enumerate(today_tasks, 1):
            print(f"  {i}. {task}")
        
        modify_today = input("Modify today's tasks? (y/n): ").strip().lower()
        if modify_today == 'y':
            new_today_tasks = self._get_task_list("today's")
            if new_today_tasks:
                self.config['TODAY_TASKS'] = json.dumps(new_today_tasks)
        
        print()
        
        # Tomorrow's tasks
        print("Tomorrow's Task List:")
        tomorrow_tasks = [
            "Top 3 Things",
            "Plan for SAFVC",
            "Zero Strikes Virgin Active",
            "All AMP Staged"
        ]
        
        print("Current tomorrow's tasks:")
        for i, task in enumerate(tomorrow_tasks, 1):
            print(f"  {i}. {task}")
        
        modify_tomorrow = input("Modify tomorrow's tasks? (y/n): ").strip().lower()
        if modify_tomorrow == 'y':
            new_tomorrow_tasks = self._get_task_list("tomorrow's")
            if new_tomorrow_tasks:
                self.config['TOMORROW_TASKS'] = json.dumps(new_tomorrow_tasks)
        
        print()
    
    def _configure_display_settings(self):
        """Configure display and formatting settings."""
        print("🎨 Display Settings")
        print("-" * 17)
        
        # Maximum items per page
        current_max = self.config.get('MAX_ITEMS_PER_PAGE', '6')
        print(f"Current max items per page: {current_max}")
        
        new_max = input("Enter maximum items per page (or press Enter to keep current): ").strip()
        if new_max:
            try:
                max_val = int(new_max)
                if 1 <= max_val <= 20:
                    self.config['MAX_ITEMS_PER_PAGE'] = str(max_val)
                else:
                    print("❌ Please enter a number between 1 and 20.")
                    self.config['MAX_ITEMS_PER_PAGE'] = current_max
            except ValueError:
                print("❌ Invalid number. Keeping current value.")
                self.config['MAX_ITEMS_PER_PAGE'] = current_max
        else:
            self.config['MAX_ITEMS_PER_PAGE'] = current_max  # Always save current value
        
        # Cover image
        current_cover = self.config.get('COVER_IMAGE_PATH', 'cover-image.jpg')
        print(f"Current cover image: {current_cover}")
        print("Note: Cover image will be scaled to reMarkable 2 dimensions (5.3\" x 7.0\")")
        print("Supported formats: JPG, PNG")
        
        new_cover = input("Enter cover image path (or press Enter to keep current): ").strip()
        if new_cover:
            cover_path = Path(new_cover)
            
            # Check if it's an absolute path or relative path
            if not cover_path.is_absolute():
                # Make it relative to the script directory
                cover_path = self.base_dir / cover_path
            
            # Validate file format
            if cover_path.suffix.lower() not in ['.jpg', '.jpeg', '.png']:
                print("⚠️ Warning: Cover image should be JPG or PNG format for best results.")
            
            if cover_path.exists():
                self.config['COVER_IMAGE_PATH'] = str(cover_path)
                print(f"✅ Cover image set to: {cover_path}")
            else:
                print("⚠️ Cover image file not found. Setting anyway (you can add the image later).")
                self.config['COVER_IMAGE_PATH'] = str(cover_path)
        else:
            self.config['COVER_IMAGE_PATH'] = current_cover  # Always save current value
        
        # Cover image enable/disable
        enable_cover = input("Enable cover page? (y/n, default: y): ").strip().lower()
        if enable_cover == 'n':
            self.config['COVER_IMAGE_PATH'] = ""
            print("✅ Cover page disabled.")
        elif enable_cover == 'y' or enable_cover == "":
            # Already handled above, cover image path is preserved
            pass
        
        print()
    
    def _get_task_list(self, day_name: str) -> List[str]:
        """Get a custom task list from user input."""
        print(f"Enter {day_name} tasks (press Enter with empty input to finish):")
        tasks = []
        
        for i in range(10):  # Max 10 tasks
            task = input(f"Task {i+1}: ").strip()
            if not task:
                break
            tasks.append(task)
        
        return tasks
    
    def _validate_ip_address(self, ip: str) -> bool:
        """Validate IP address format."""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not (0 <= int(part) <= 255):
                    return False
            return True
        except ValueError:
            return False
    
    def _validate_calendar_url(self, url: str) -> bool:
        """Validate calendar URL format."""
        try:
            parsed = urlparse(url)
            return (
                parsed.scheme in ['http', 'https'] and
                bool(parsed.netloc) and
                ('calendar' in url.lower() or 'ical' in url.lower() or url.endswith('.ics'))
            )
        except Exception:
            return False
    
    def _save_calendar_feeds(self, feeds: List[str]):
        """Save calendar feeds to file."""
        try:
            with open(self.calendar_feeds_file, 'w', encoding='utf-8') as f:
                f.write("# Calendar Feed URLs\n")
                f.write("# Add your calendar feed URLs here, one per line\n")
                f.write("# Lines starting with # are comments\n\n")
                
                for feed in feeds:
                    f.write(f"{feed}\n")
            
            logging.info(f"✅ Saved {len(feeds)} calendar feeds to {self.calendar_feeds_file}")
        except Exception as e:
            logging.error(f"❌ Could not save calendar feeds: {e}")
    
    def _save_configuration(self):
        """Save configuration to .env file."""
        try:
            # Backup existing .env file
            if self.env_file.exists():
                backup_path = self.env_file.with_suffix('.env.backup')
                import shutil
                shutil.copy2(self.env_file, backup_path)
                logging.info(f"📋 Backed up existing .env to {backup_path}")
            
            # Write new configuration
            with open(self.env_file, 'w', encoding='utf-8') as f:
                f.write("# Dashboard For Export Configuration\n")
                f.write(f"# Generated on {self._get_timestamp()}\n\n")
                
                # Write configuration variables
                for key, value in sorted(self.config.items()):
                    f.write(f'{key}="{value}"\n')
            
            logging.info(f"✅ Configuration saved to {self.env_file}")
            
        except Exception as e:
            logging.error(f"❌ Could not save configuration: {e}")
            raise
    
    def _get_timestamp(self) -> str:
        """Get current timestamp for configuration file."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def main():
    """Main entry point."""
    try:
        configurator = DashboardConfigurator()
        configurator.run()
    except KeyboardInterrupt:
        print("\n\n👋 Configuration cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Configuration failed: {e}")
        logging.error(f"Configuration error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
