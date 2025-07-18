#!/usr/bin/env python3
"""
Fresh Repository Setup Script
============================
Run this script to set up the reMarkable Dashboard Generator in a new environment.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.8 or higher"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def check_dependencies():
    """Check and install required dependencies"""
    print("\n📦 Checking dependencies...")
    
    requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        print("❌ requirements.txt not found")
        return False
    
    try:
        # Check if we're in a virtual environment
        in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
        if not in_venv:
            print("⚠️  Not in a virtual environment. Consider using:")
            print("   python -m venv venv")
            print("   venv\\Scripts\\activate  (Windows)")
            print("   source venv/bin/activate  (Linux/Mac)")
            print()
        
        # Install requirements
        print("Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True, capture_output=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def create_config_files():
    """Create configuration files from templates"""
    print("\n📝 Setting up configuration files...")
    
    # Create .env from .env.example
    env_example = Path(".env.example")
    env_file = Path(".env")
    
    if env_example.exists() and not env_file.exists():
        shutil.copy(env_example, env_file)
        print("✅ Created .env from template")
    elif env_file.exists():
        print("⚠️  .env already exists, skipping")
    else:
        print("❌ .env.example not found")
        return False
    
    # Create calendar_feeds.txt from calendar_feeds.txt.example
    calendar_example = Path("calendar_feeds.txt.example")
    calendar_file = Path("calendar_feeds.txt")
    
    if calendar_example.exists() and not calendar_file.exists():
        shutil.copy(calendar_example, calendar_file)
        print("✅ Created calendar_feeds.txt from template")
    elif calendar_file.exists():
        print("⚠️  calendar_feeds.txt already exists, skipping")
    else:
        print("❌ calendar_feeds.txt.example not found")
        return False
    
    return True

def check_required_files():
    """Check that all required files exist"""
    print("\n📁 Checking required files...")
    
    required_files = [
        "Dashboard For Export.py",
        "setup_dashboard_export.py", 
        "dashboard_template.html",
        "requirements.txt"
    ]
    
    missing_files = []
    for file in required_files:
        if Path(file).exists():
            print(f"✅ {file}")
        else:
            print(f"❌ {file} - MISSING")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n❌ Missing required files: {missing_files}")
        return False
    
    return True

def run_configuration():
    """Run the interactive configuration script"""
    print("\n🔧 Running interactive configuration...")
    
    config_script = Path("setup_dashboard_export.py")
    if not config_script.exists():
        print("❌ setup_dashboard_export.py not found")
        return False
    
    try:
        subprocess.run([sys.executable, str(config_script)], check=True)
        print("✅ Configuration completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Configuration failed: {e}")
        return False
    except KeyboardInterrupt:
        print("\n⚠️  Configuration cancelled by user")
        return False

def main():
    """Main setup function"""
    print("🚀 reMarkable Dashboard Generator Setup")
    print("======================================")
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Check required files exist
    if not check_required_files():
        return False
    
    # Install dependencies
    if not check_dependencies():
        return False
    
    # Create config files
    if not create_config_files():
        return False
    
    # Run configuration
    print("\n🎯 Ready to configure your dashboard settings!")
    print("This will set up your reMarkable connection, calendars, and preferences.")
    
    response = input("\nRun interactive configuration now? (y/n): ").lower().strip()
    if response in ['y', 'yes']:
        if not run_configuration():
            return False
    else:
        print("⚠️  Skipping configuration. Run 'python setup_dashboard_export.py' later.")
    
    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. If you skipped configuration, run: python setup_dashboard_export.py")
    print("2. Generate your first dashboard: python 'Dashboard For Export.py'")
    print("3. Check the generated PDF in your configured output directory")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
