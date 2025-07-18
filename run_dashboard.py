"""
Quick fix script to load .env file and run the dashboard
"""
import os
from pathlib import Path

def load_env_file():
    """Load environment variables from .env file"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        print(f"✅ Loaded environment from {env_file}")
    else:
        print(f"❌ No .env file found at {env_file}")

if __name__ == "__main__":
    # Load .env first
    load_env_file()
    
    # Then import and run the main script
    import huang_di
    huang_di.main()
