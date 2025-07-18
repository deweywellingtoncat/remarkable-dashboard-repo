# Huang Di Dashboard - Quick Setup Guide

## 🚀 Quick Start

### Option 1: Interactive Setup (Recommended)
1. **Windows**: Double-click `setup_dashboard.bat`
2. **Mac/Linux**: Run `python setup_dashboard.py`
3. Follow the interactive prompts

### Option 2: Manual Setup
1. Copy `.env.example` to `.env` and edit your settings
2. Copy `calendar_feeds.txt.example` to `calendar_feeds.txt` and add your URLs

## 📋 What You'll Need

### Google Calendar URLs
1. Go to [Google Calendar](https://calendar.google.com)
2. Click the ⋯ menu next to your calendar name
3. Select "Settings and sharing"
4. Scroll to "Integrate calendar"
5. Copy the **"Secret address in iCal format"** URL
6. ⚠️ **Important**: Use the PRIVATE URL (contains "private-"), not the public one!

### reMarkable Device (Optional)
- Your reMarkable's IP address (find in Settings > Help > General Information)
- SSH key for automatic PDF upload (see SSH setup below)

### Location Coordinates
- Home and work coordinates for weather (the setup script can help find these)
- Or use city names and let the script look them up automatically

### Cover Image (Optional)
- A custom image for your dashboard cover page
- Supported formats: JPG, PNG
- Recommended size: 1404x1872 pixels (reMarkable 2 resolution)
- Place as `cover-image.jpg` or `cover-image.png` in the main directory

## 🔐 SSH Setup for reMarkable (Advanced)

### Quick Setup
```bash
# Generate SSH key
ssh-keygen -t rsa -b 4096 -f ~/.ssh/remarkable

# Copy to reMarkable (using your IP)
ssh-copy-id -i ~/.ssh/remarkable.pub root@192.168.1.96

# Test connection
ssh -i ~/.ssh/remarkable root@192.168.1.96
```

### Detailed Instructions
1. Enable SSH on your reMarkable (Developer settings)
2. Generate an SSH key on your computer
3. Copy the public key to your reMarkable
4. Test the connection

For more details: [reMarkable SSH Guide](https://remarkablewiki.com/tech/ssh)

## ⚙️ Configuration Options

### Example Settings (Pre-filled for Your Setup)

#### Device & Output
- **reMarkable IP**: 192.168.1.96
- **Backup IP**: 10.11.99.1
- **SSH Key**: C:/Users/%USERNAME%/.ssh/id_rsa
- **Output Path**: G:/My Drive/Huang_Di

#### Location & Weather
- **Timezone**: Asia/Singapore
- **Home**: 1.29, 103.85
- **Work**: 1.37, 103.82

#### Calendar Feeds (calendar_feeds.txt)
```
https://calendar.google.com/calendar/ical/your-calendar/private-abc123/basic.ics
https://outlook.office365.com/owa/calendar/your-calendar/private-def456/reachcalendar.ics
```

#### Personalization
- **Epigraph Quote**: The LORD is my strength, and my song, and is become my salvation.
- **Epigraph Author**: (leave blank or set as desired)
- **Max Items Per Page**: 6

### Environment Variables (.env)
```bash
# Device Settings
REMARKABLE_IP=192.168.1.96
REMARKABLE_BACKUP_IP=10.11.99.1
REMARKABLE_SSH_KEY=C:/Users/%USERNAME%/.ssh/id_rsa
REMARKABLE_USER=root

# Location & Weather
TIMEZONE=Asia/Singapore
HOME_LAT=1.29
HOME_LON=103.85
WORK_LAT=1.37
WORK_LON=103.82

# File Locations
LOCAL_OUTPUT_PATH=G:/My Drive/Huang_Di
MAX_ITEMS_PER_PAGE=6

# Personalization
EPIGRAPH_QUOTE=The LORD is my strength, and my song, and is become my salvation.
EPIGRAPH_AUTHOR=
```

### Calendar Feeds (calendar_feeds.txt)
```
https://calendar.google.com/calendar/ical/your-calendar/private-abc123/basic.ics
https://outlook.office365.com/owa/calendar/your-calendar/private-def456/reachcalendar.ics
```

## 🧪 Testing Your Setup

### Test Calendar Connection
```bash
python -c "
import requests
url = 'YOUR_CALENDAR_URL_HERE'
r = requests.get(url)
print('✅ Calendar accessible' if r.status_code == 200 else '❌ Calendar failed')
"
```

### Test reMarkable Connection
```bash
# Ping test
ping 192.168.1.96

# SSH test (if configured)
ssh -i ~/.ssh/remarkable root@192.168.1.96 echo "Connection successful"
```

### Test Weather API
```bash
python -c "
import requests
url = 'https://api.open-meteo.com/v1/forecast?latitude=1.29&longitude=103.85&daily=temperature_2m_max'
r = requests.get(url)
print('✅ Weather API accessible' if r.status_code == 200 else '❌ Weather API failed')
"
```

## 🎯 Running the Dashboard

### Generate Dashboard
```bash
python huang_di.py
```

### Schedule Automatic Generation
```bash
# Windows
python schedule_huang_di.bat

# Or manually add to Task Scheduler
```

## 🆘 Troubleshooting

### Common Issues

**"Calendar feeds not found"**
- Make sure `calendar_feeds.txt` exists and contains valid URLs
- Check that URLs are private iCal URLs, not public ones

**"reMarkable not reachable"**
- Verify the IP address in your reMarkable settings
- Make sure both devices are on the same network
- Check if SSH is enabled on the reMarkable

**"Weather data unavailable"**
- Check your internet connection
- Verify latitude/longitude coordinates are correct
- Make sure coordinates are in decimal format (e.g., 40.7128, not 40°42'46"N)

**"Template not found"**
- Make sure `dashboard_template.html` exists in the project directory
- Check file permissions

**Cover image issues**
- Ensure image is named exactly `cover-image.jpg` or `cover-image.png`
- Check file size (very large images may cause PDF generation to fail)
- Verify image format is JPG or PNG
- Try a smaller image if PDF generation is slow

### Getting Help

1. Check the log file: `dashboard_run.log`
2. Run with verbose output: `python huang_di.py --verbose`
3. Test individual components using the setup script's test function

## 📁 File Structure

After setup, your directory should look like:
```
huang_di_project/
├── huang_di.py                 # Main script
├── setup_dashboard.py          # Setup wizard
├── setup_dashboard.bat         # Windows setup launcher
├── schedule_huang_di.bat       # Windows scheduler
├── dashboard_template.html     # PDF template
├── cover-image.jpg             # Your cover image (optional)
├── .env                        # Your configuration (created by setup)
├── calendar_feeds.txt          # Your calendar URLs (created by setup)
├── .env.example               # Example configuration
├── calendar_feeds.txt.example # Example calendar file
├── .gitignore                 # Git ignore file
└── README.md                  # Full documentation
```

## 🎨 Customization

### Personalizing Your Dashboard
- Edit `EPIGRAPH_QUOTE` and `EPIGRAPH_AUTHOR` in `.env`
- Add a custom cover image as `cover-image.jpg` or `cover-image.png`
- Modify `dashboard_template.html` for layout changes
- Add/remove calendar feeds in `calendar_feeds.txt`
- Adjust `MAX_ITEMS_PER_PAGE` for more/fewer items per page

### Adding More Locations
Currently supports two weather locations (🏠 Home, 🏯 Work). To add more:
1. Edit the `LOCATIONS` dictionary in `huang_di.py`
2. Add corresponding LAT/LON environment variables
3. Update the template if needed

---

**Need more help?** Check the full README.md or create an issue on GitHub.
