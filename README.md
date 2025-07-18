# reMarkable Dashboard Generator

A robust, production-ready daily dashboard generator for reMarkable 2 devices with comprehensive weather forecasting, multi-calendar support, and automation-hardened architecture.

## ✨ Latest Updates (v3.1) - Automation Hardening & Stability

### 🔄 Automation Excellence
- **Automation Mode Detection**: Automatically detects scheduled/unattended execution environments
- **Emergency Dashboard**: Creates minimal fallback dashboard when primary generation fails
- **Comprehensive Error Handling**: Graceful degradation ensures automation never completely fails
- **Windows Task Scheduler Ready**: Robust .bat script with pre-flight checks and detailed logging

### 🛡️ Production Stability Features
- **Defensive Programming**: All external API calls, file operations, and data parsing protected with try-catch
- **Local PDF Saving**: Guaranteed local backup with directory creation and error recovery
- **Network Resilience**: Continues with cached/fallback data when internet is unavailable
- **SSH Failure Tolerance**: Dashboard generation succeeds even if reMarkable upload fails

### 🏗️ Architecture Overhaul
- **Modular Design**: Massive 200+ line main() function broken into focused, single-responsibility functions
- **Clean Configuration**: Type-safe configuration system with dataclasses and environment validation
- **Enhanced Error Handling**: Custom exception hierarchy with graceful degradation and circuit breakers
- **Streamlined Data Flow**: Clear separation between initialization, data fetching, processing, and output generation

### 🔧 Code Quality Improvements
- **Type Safety**: Full type annotations with dataclasses for configuration management
- **Error Isolation**: Individual function failures don't crash the entire system
- **Testability**: Each component can now be unit tested independently
- **Maintainability**: Clean separation of concerns makes debugging and modifications much easier

### 🎨 User Experience Enhancements
- **Interactive Setup Wizard**: Complete configuration through guided prompts
- **Cover Image Support**: Custom cover pages with JPG/PNG images scaled for reMarkable 2
- **Smart File Management**: Automatic image copying, naming, and validation
- **Cross-Platform Compatibility**: File browser integration with graceful fallbacks

### 🛡️ Robust Error Handling
- **Custom Exceptions**: `DataFetchError`, `EventProcessingError`, `PDFGenerationError`, `UploadError`
- **Graceful Degradation**: System continues with partial data when external services fail
- **Emergency Fallback**: Creates minimal dashboard when main process encounters critical errors
- **Context-Aware Logging**: Detailed error context with operation-level tracking

### 🌤️ Weather System Redesign
- **Simplified Processing**: Reduced weather code from ~200 lines to ~80 lines while maintaining output
- **Better Error Recovery**: Weather failures don't prevent dashboard generation
- **Consistent Output**: Maintains exact same format: "20–30°C; Rain 5.2mm, likely 08-17, Peak 80% @ 14; UV 8"
- **Location Management**: Clean location configuration with coordinate validation

### 📅 Event Processing Enhancements
- **Modular Event Handling**: Separate functions for parsing, filtering, and template processing
- **Robust Cancellation Detection**: Multi-layer event cancellation and override handling
- **Better Timezone Support**: Improved RRULE processing with timezone conversion
- **Event Validation**: Comprehensive validation prevents malformed events from causing failures

## 🚀 Quick Start

### Option 1: Interactive Setup (Recommended)

**Windows Users:**
1. Double-click `setup_dashboard.bat`
2. Follow the interactive prompts

**Mac/Linux Users:**
```bash
python setup_dashboard.py
```

The setup wizard will guide you through:
- 📱 reMarkable device configuration
- 📅 Google Calendar integration  
- 🌍 Weather location setup
- 🖼️ Cover image configuration (optional)
- ⚙️ Personal preferences

### Option 2: Manual Setup

### 1. Environment Setup
```powershell
# Copy and customize environment file
Copy-Item .env.example .env
# Edit .env with your settings

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration
Edit your `.env` file:
```bash
# reMarkable Device
REMARKABLE_IP=192.168.1.96
REMARKABLE_BACKUP_IP=10.11.99.1
REMARKABLE_SSH_KEY=C:\Users\%USERNAME%\.ssh\id_rsa
REMARKABLE_USER=root

# Location & Weather
TIMEZONE=Asia/Singapore
HOME_LAT=1.29
HOME_LON=103.85
WORK_LAT=1.37
WORK_LON=103.82

# File Paths
LOCAL_OUTPUT_PATH=G:\My Drive\Huang_Di
CALENDAR_FEEDS_FILE=calendar_feeds.txt

# Performance Tuning
MAX_ITEMS_PER_PAGE=6
DOWNLOAD_RETRIES=3
REQUEST_TIMEOUT_SECONDS=15
REMOTE_COMMAND_TIMEOUT_SECONDS=20

# Optional Features
EPIGRAPH_QUOTE=The LORD is my strength, and my song, and is become my salvation.
EPIGRAPH_AUTHOR=
```

### 3. Calendar Setup
Edit `calendar_feeds.txt` with your calendar URLs:
```
https://calendar.google.com/calendar/ical/your-calendar/basic.ics
https://outlook.office365.com/owa/calendar/your-calendar/reachcalendar.ics
# Add more calendars as needed
```

### 4. Cover Image Setup (Optional)
Add a custom cover image for your dashboard:
```bash
# Place your image file in the project directory as:
cover-image.jpg    # For JPEG images
# OR
cover-image.png    # For PNG images

# Recommended specifications:
# - Format: JPG or PNG
# - Size: 1404x1872 pixels (reMarkable 2 resolution)
# - File size: Under 10MB for best performance
```

### 5. Test Connection
```powershell
python huang_di.py --test-connection
```

### 6. Run Dashboard
```powershell
python huang_di.py
```

## 🤖 Automation Setup

### Windows Task Scheduler (Recommended)

1. **Use the Robust Script**
   ```powershell
   # Use the provided automation script with comprehensive error handling
   .\run_huang_di_robust.bat
   ```

2. **Setup Task Scheduler**
   ```powershell
   # Open Task Scheduler
   taskschd.msc
   
   # Create Basic Task with these settings:
   # - Name: "Huang Di Dashboard"
   # - Trigger: Daily at 6:00 AM
   # - Action: Start a program
   # - Program: C:\path\to\your\run_huang_di_robust.bat
   # - Start in: C:\path\to\your\huang_di_directory
   ```

3. **Task Scheduler Best Practices**
   - **Run whether user is logged on or not**: ✅ Check this
   - **Run with highest privileges**: ✅ Check this
   - **Configure for**: Windows 10/11
   - **Stop if runs longer than**: 1 hour (safety timeout)

### Automation Features

#### Pre-flight Checks
- ✅ Python availability verification
- ✅ Script file existence validation
- ✅ Network connectivity testing
- ✅ Dependencies verification

#### Error Handling
- 🛡️ **Graceful Degradation**: Continues with partial data when services fail
- 🆘 **Emergency Dashboard**: Creates minimal dashboard if all else fails
- 📝 **Comprehensive Logging**: Detailed logs for troubleshooting
- 🔄 **Non-blocking Failures**: Upload failures don't stop PDF generation

#### Local PDF Backup
```env
# Ensure local output is configured
LOCAL_OUTPUT_PATH=G:/My Drive/Huang_Di
```

### Monitoring & Maintenance

#### Daily Checks
```powershell
# Check if automation ran successfully
Get-Content automation_run.log | Select-String "✅"

# Verify PDF was created
Get-ChildItem "G:\My Drive\Huang_Di\*.pdf" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

#### Weekly Maintenance
```powershell
# Clear old automation logs (keep last 30 days)
Get-ChildItem *.log | Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-30)} | Remove-Item

# Update dependencies
pip install --upgrade -r requirements.txt
```

#### Monthly Health Check
```powershell
# Test complete pipeline manually
python huang_di.py --automation

# Verify all components
python -c "
from huang_di import Config, pre_flight_checks
pre_flight_checks()
print('All systems operational')
"
```

### Automation Modes

#### Command Line Flags
```powershell
# Force automation mode
python huang_di.py --automation

# Test mode (no upload)
python huang_di.py --test-mode

# Verbose logging
python huang_di.py --verbose
```

#### Environment Detection
The script automatically detects automation mode when:
- ✅ Running in Windows Task Scheduler
- ✅ No interactive terminal available
- ✅ `AUTOMATION_MODE=true` environment variable set
- ✅ Running in CI/CD environment

## 🏗️ Refactored Architecture

### Main Components

#### 1. **Application Orchestrator**
```python
def main() -> None:
    """15-line main function - clear workflow overview"""
    setup_logging()
    config_data = initialize_application()       # Setup & validation
    external_data = fetch_external_data()        # Calendar & weather
    dashboard_data = process_dashboard_data()     # Parse & organize
    generate_and_distribute_output()             # PDF & upload
```

#### 2. **Configuration Management**
```python
@dataclass
class AppConfig:
    """Type-safe configuration with validation"""
    # Network settings
    download_retries: int = 3
    request_timeout_seconds: int = 15
    
    # reMarkable settings  
    remarkable_ips: List[str]
    remarkable_ssh_key: Path
    
    # Location settings
    locations: Dict[str, tuple]
    timezone_local_str: str
```

#### 3. **Modular Data Processing**
- **`fetch_external_data()`**: Concurrent calendar and weather fetching
- **`process_events_from_ics()`**: Event parsing and filtering by day
- **`process_weather_for_display()`**: Weather narrative generation
- **`build_all_page_contexts()`**: Page layout and context creation

#### 4. **Enhanced Error Handling**
```python
@with_error_handling("operation_name", fallback_value=[], reraise=False)
def fetch_data():
    """Decorator-based consistent error handling"""
    pass

with error_context("PDF generation"):
    """Context manager for operation-level error tracking"""
    generate_pdf()
```

### Data Flow Architecture
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Calendar APIs │    │   Weather APIs  │    │   Config Files  │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
    ┌─────────────────────────────────────────────────────────┐
    │          fetch_external_data()                          │
    │  • Concurrent fetching    • Error isolation            │
    │  • Retry logic           • Graceful degradation        │
    └─────────────────────┬───────────────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────────────┐
    │        process_dashboard_data()                         │
    │  • Event filtering       • Weather processing          │
    │  • Template preparation  • Page context building       │
    └─────────────────────┬───────────────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────────────┐
    │      generate_and_distribute_output()                   │
    │  • PDF generation       • Local copy saving            │
    │  • reMarkable upload     • Error recovery               │
    └─────────────────────────────────────────────────────────┘
```

## 🔧 Automation Setup

### Windows Scheduled Task
```powershell
# Create scheduled task for 6 AM daily
schtasks /create /tn "Remarkable Dashboard" /tr "python C:\AI Prompt Local\huang_di.py" /sc daily /st 06:00
```

### Docker Deployment
```bash
# Build and run
docker build -t remarkable-dashboard .
docker run -d --env-file .env -v "G:\My Drive\Huang_Di:/output" remarkable-dashboard

# View logs
docker logs remarkable-dashboard
```

### Linux Cron
```bash
# Add to crontab for 6 AM daily
0 6 * * * cd /path/to/dashboard && python huang_di.py >> logs/cron.log 2>&1
```

## 📋 Configuration Reference

### Environment Variables

#### Core Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `REMARKABLE_IP` | `192.168.1.96` | Primary reMarkable IP |
| `REMARKABLE_BACKUP_IP` | `10.11.99.1` | Fallback IP address |
| `REMARKABLE_SSH_KEY` | `~/.ssh/id_rsa` | SSH private key path |
| `TIMEZONE` | `Asia/Singapore` | Local timezone |
| `LOCAL_OUTPUT_PATH` | `G:\My Drive\Huang_Di` | Local copy destination |

#### Performance Tuning
| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_ITEMS_PER_PAGE` | `6` | Events/tasks per page |
| `DOWNLOAD_RETRIES` | `3` | Network retry attempts |
| `REQUEST_TIMEOUT_SECONDS` | `15` | HTTP request timeout |
| `REMOTE_COMMAND_TIMEOUT_SECONDS` | `20` | SSH command timeout |
| `CONNECTION_TIMEOUT_SECONDS` | `5` | Initial connection timeout |

#### Weather Locations
| Variable | Default | Description |
|----------|---------|-------------|
| `HOME_LAT` | `1.29` | Home latitude |
| `HOME_LON` | `103.85` | Home longitude |
| `WORK_LAT` | `1.37` | Work latitude |
| `WORK_LON` | `103.82` | Work longitude |

#### Personalization & Visual Options
| File/Variable | Default | Description |
|---------------|---------|-------------|
| `cover-image.jpg` | _(none)_ | Cover page image (JPG format) |
| `cover-image.png` | _(none)_ | Cover page image (PNG format) |
| `EPIGRAPH_QUOTE` | _(Bible verse)_ | Daily quote/epigraph |
| `EPIGRAPH_AUTHOR` | _(empty)_ | Quote attribution |

**Cover Image Requirements:**
- **Format**: JPG or PNG
- **Recommended Size**: 1404x1872 pixels (reMarkable 2 resolution)
- **File Size**: Under 10MB for optimal performance
- **Location**: Place in project root directory

## 🔍 Monitoring & Troubleshooting

### Health Checks
```powershell
# Configuration validation
python -c "from huang_di import Config, validate_config; print(validate_config())"

# Connection test
python -c "from huang_di import check_remarkable_availability; print(check_remarkable_availability())"

# Weather API test
python -c "from huang_di import get_weather_data; print(get_weather_data())"
```

### Logging Levels
- **Automation Mode**: DEBUG level with structured logging
- **Interactive Mode**: INFO level with console output
- **Error Isolation**: Each component logs independently

### Common Issues & Solutions

#### SSH Connection Failed
```powershell
# Test connection
ssh -i $env:REMARKABLE_SSH_KEY root@$env:REMARKABLE_IP "echo 'Connected'"

# Check key permissions (should be 600)
icacls $env:REMARKABLE_SSH_KEY

# Generate new key pair
ssh-keygen -t rsa -b 2048 -f ~/.ssh/id_rsa_remarkable
```

#### Calendar Fetch Failures
```powershell
# Check calendar feeds file
Get-Content calendar_feeds.txt

# Test individual URL
curl "https://your-calendar-url.ics"

# Validate feeds configuration
python -c "from huang_di import Config; print(f'Loaded {len(Config.ical_feeds)} feeds')"
```

#### Weather API Issues
```powershell
# Test coordinates
python -c "from huang_di import Config; print(Config.locations)"

# Manual weather fetch
python -c "from huang_di import fetch_weather_for_location_safe; print(fetch_weather_for_location_safe(('🏠', (1.29, 103.85))))"
```

#### PDF Generation Problems
```powershell
# Check template
Test-Path "dashboard_template.html"

# Check cover image (if using)
Test-Path "cover-image.jpg"
Test-Path "cover-image.png"

# Validate page contexts
python -c "from huang_di import build_all_page_contexts; print('Template validation OK')"
```

#### Cover Image Issues
```powershell
# Check image file exists and is readable
Test-Path "cover-image.jpg" -PathType Leaf
Get-Item "cover-image.jpg" | Select-Object Length, Extension

# Test image size (should be under 10MB for best performance)
$size = (Get-Item "cover-image.jpg").Length / 1MB
if ($size -gt 10) { Write-Warning "Large image file may slow PDF generation" }

# Verify image format
file "cover-image.jpg"  # Linux/Mac
```

## 📈 Performance Features

### Error Recovery Strategies
1. **Individual Function Isolation**: Calendar failure doesn't prevent weather fetching
2. **Graceful Degradation**: Missing data replaced with placeholder content
3. **Emergency Fallback**: Minimal dashboard created when main process fails
4. **Retry Logic**: Exponential backoff for network operations
5. **Timeout Protection**: All operations have reasonable time limits

### Resource Management
- **Concurrent Processing**: Weather locations fetched in parallel
- **Memory Efficiency**: Streaming event processing for large calendars
- **Disk Space Monitoring**: Automatic cleanup of temporary files
- **Connection Pooling**: Efficient SSH connection management

### Monitoring Metrics
- **Execution Time**: Total runtime and per-component timing
- **Success Rates**: Track success/failure rates for each data source
- **Error Patterns**: Categorized error reporting for debugging
- **Resource Usage**: Memory and disk space monitoring

## 🛡️ Security & Reliability

### Security Features
- **Environment-based Secrets**: No hardcoded credentials
- **SSH Key Validation**: Automatic key permission checking
- **Path Validation**: Secure file path handling
- **Input Sanitization**: Calendar data validation and sanitization

### Reliability Features
- **Circuit Breakers**: Automatic service isolation during outages
- **Health Monitoring**: Pre-flight checks before execution
- **Atomic Operations**: PDF generation and upload as atomic operations
- **Backup Strategies**: Multiple IP addresses and fallback paths

### Data Protection
- **Local Backups**: Automatic local copy saving
- **Version Management**: Timestamped file naming
- **Error Logs**: Comprehensive logging without sensitive data exposure
- **Graceful Shutdown**: Proper cleanup on interruption

## 🔄 Development & Testing

### Code Structure
```
huang_di.py
├── Configuration Management (AppConfig dataclass)
├── Error Handling (Custom exceptions & decorators)
├── Data Fetching (Modular fetch functions)
├── Event Processing (Parse, filter, validate)
├── Weather Processing (Fetch, process, format)
├── Page Building (Context creation, layout)
├── PDF Generation (Template rendering, validation)
└── Upload Management (SSH, file transfer, restart)
```

### Testing Strategy
```powershell
# Unit test individual components
python -c "from huang_di import process_weather_for_display; print('Weather processing OK')"

# Integration test full pipeline
python huang_di.py --dry-run

# End-to-end test
python huang_di.py --test-mode
```

### Debugging Tools
```powershell
# Enable debug logging
$env:DEBUG = "true"
python huang_di.py

# Configuration summary
python -c "from huang_di import get_config_summary; print(get_config_summary())"

# Component health check
python -c "from huang_di import validate_config; print(validate_config())"
```

## 📊 Output Format

### Dashboard Structure
1. **Cover Page** (optional): Custom image scaled for reMarkable 2
2. **Today's Page(s)**: Events, tasks, weather, planning space
3. **Today's Notes**: Blank page with gray box for handwritten notes
4. **Tomorrow's Page(s)**: Events, tasks, weather preview
5. **Tomorrow's Notes**: Blank page for advance planning

### Weather Display Format
```
🏠 20–30°C; Rain 5.2mm, likely 08-17, Peak 80% @ 14; UV 8
🏯 18–28°C; No rain expected; UV 7
```

### File Naming Convention
- **PDF**: `NMS_YYYY_MM_DD_D.pdf` (e.g., `NMS_2025_07_09_W.pdf`)
- **Display**: `NMS_D_MMM_YY` (e.g., `NMS_9_Jul_25`)
- **Local Copy**: Saved to configured `LOCAL_OUTPUT_PATH`

## 🤝 Contributing

### Development Setup
1. Fork the repository
2. Set up development environment with `.env.dev`
3. Run tests: `python -m pytest tests/`
4. Check code quality: `python -m flake8 huang_di.py`

### Adding Features
1. **New Data Sources**: Add to `fetch_external_data()`
2. **Processing Logic**: Extend `process_dashboard_data()`
3. **Output Formats**: Modify `generate_and_distribute_output()`
4. **Error Handling**: Use `@with_error_handling` decorator

### Code Standards
- **Type Annotations**: All functions must have type hints
- **Error Handling**: Use custom exceptions and decorators
- **Logging**: Structured logging with operation context
- **Documentation**: Comprehensive docstrings and comments

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 📚 Technical Documentation

### Function Reference

#### Core Orchestration
- `main()`: 15-line orchestrator function
- `initialize_application()`: Configuration and validation
- `fetch_external_data()`: Concurrent data fetching
- `process_dashboard_data()`: Data processing and organization
- `generate_and_distribute_output()`: PDF creation and distribution
  - `save_local_copy()`: Local PDF backup to configured directory
  - `upload_to_remarkable()`: SSH upload with metadata generation

#### Configuration Management
- `AppConfig.load_from_env()`: Environment-based configuration loading
- `validate_config()`: Configuration validation and issue reporting
- `get_config_summary()`: Debug-friendly configuration overview

#### Data Processing
- `fetch_and_process_calendars()`: Multi-calendar ICS fetching
- `get_weather_data()`: Concurrent weather API calls
- `parse_events()`: Event parsing with cancellation handling
- `process_weather_for_display()`: Weather narrative generation

#### Page Building
- `build_all_page_contexts()`: Complete page layout generation
- `build_today_section()` / `build_tomorrow_section()`: Day-specific page building
- `create_content_page_context()`: Standardized page context creation

#### Error Handling
- `@with_error_handling()`: Decorator for consistent error handling
- `error_context()`: Context manager for operation tracking
- `create_emergency_dashboard()`: Fallback dashboard generation

### Error Handling Hierarchy
```
DashboardError (Base)
├── DataFetchError (External API failures)
├── EventProcessingError (Calendar parsing issues)
├── PDFGenerationError (Template/rendering problems)
└── UploadError (SSH/network issues)
```

This documentation reflects the major refactoring improvements that make the codebase more maintainable, reliable, and easier to work with.
