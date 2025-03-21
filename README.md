# Google Android OTA and Factory Image Scraper

A powerful Python tool for downloading and managing Google Android OTA and factory images. This tool allows you to easily fetch, filter, and download official Android system images for Google devices (Pixel, Nexus).

## Features

- Download both OTA and factory images for Google devices
- Support for modern Pixel devices and legacy Nexus devices
- Smart filtering options (beta, carrier-specific, region-specific builds)
- Interactive build picker in terminal mode
- Automatic checksum verification
- Caching system to reduce server load
- Colored terminal output
- JSON output support for automation
- Device family grouping and analysis
- Progress bars for downloads
- Comprehensive logging

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/google-ota-download.git
cd google-ota-download
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Download latest OTA image for a device
python download.py --device husky

# Download latest factory image for a device
python download.py --device husky --factory

# Download specific build
python download.py --device husky --build BP1A.250305.019

# Interactive build picker
python download.py --device husky --build
```

### Advanced Options

```bash
# Include beta builds
python download.py --device husky --include-beta

# Include carrier-specific builds
python download.py --device husky --include-carrier

# Filter by carrier
python download.py --device husky --include-carrier --carrier Verizon

# Download to specific location
python download.py --device husky --output /path/to/save/

# Skip hash verification
python download.py --device husky --no-verify-hash

# Output in JSON format
python download.py --device husky --json
```

### Device Families

```bash
# List all device families
python download.py --list-families

# Check updates for entire device family
python download.py --family pixel8

# Analyze update status for a family
python download.py --family pixel8 --analyze-family
```

### Cache Management

```bash
# Show cache statistics
python download.py --cache-stats

# Clear cache
python download.py --clear-cache
```

## Command Line Arguments

| Argument | Description |
|----------|-------------|
| `--device`, `-d` | Device codename to check |
| `--family`, `-f` | Device family to check (e.g., pixel8, pixel7) |
| `--factory` | Download factory image instead of OTA |
| `--build`, `-b` | Specific build number to download |
| `--include-beta` | Include beta builds |
| `--include-carrier` | Include carrier-specific builds |
| `--include-region` | Include region-specific builds |
| `--carrier` | Filter for specific carrier |
| `--region` | Filter for specific region |
| `--output`, `-o` | Download path |
| `--json` | Output results in JSON format |
| `--debug` | Enable debug logging |
| `--non-interactive` | Force non-interactive mode |

## Supported Devices

### Pixel Series
- Pixel 8 Pro (husky)
- Pixel 8 (shiba)
- Pixel 7 Pro (cheetah)
- Pixel 7 (panther)
- Pixel 7a (lynx)
- Pixel 6 Pro (raven)
- Pixel 6 (oriole)
- Pixel 6a (bluejay)
- Pixel 5 (redfin)
- Pixel 5a (barbet)
- Pixel 4 XL (coral)
- Pixel 4 (flame)
- Pixel 4a (sunfish)
- Pixel 4a 5G (bramble)
- And more...

### Special Devices
- Pixel Fold (felix)
- Pixel Tablet (tangorpro)

### Legacy Devices
- Various Nexus devices

## Examples

### Download Latest Stable OTA

```bash
python download.py --device husky --output ./downloads/
```

### Download Specific Factory Image with Carrier Filter

```bash
python download.py --device husky --factory --build BP1A.250305.019 --carrier Verizon
```

### Analyze Family Update Status

```bash
python download.py --family pixel8 --analyze-family --json
```

## Error Handling

The tool includes comprehensive error handling:
- Automatic retries for failed downloads
- Checksum verification
- Cache validation
- Network error handling
- Invalid device/build detection

## Logging

Logs are stored in `android_images.log` with the following levels:
- DEBUG: Detailed debugging information
- INFO: General operational information
- WARNING: Warning messages
- ERROR: Error messages
- CRITICAL: Critical errors

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Google Android OTA and Factory Images pages
- BeautifulSoup4 for HTML parsing
- Colorama for terminal colors
- Requests for HTTP handling

## Disclaimer

This tool is not affiliated with, endorsed by, or related to Google in any way. Use at your own risk and responsibility. 