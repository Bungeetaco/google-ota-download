#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import re
import json
import os
import datetime
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from http.cookies import SimpleCookie
import hashlib
import sys
from colorama import init, Fore, Back, Style

# Initialize colorama for cross-platform color support
init()

# Custom formatter for colored output
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored output"""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Back.WHITE
    }
    
    def format(self, record):
        # Add color to the level name
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{Style.RESET_ALL}"
        
        # Add color to the message based on level
        if record.levelname in self.COLORS:
            record.msg = f"{self.COLORS[record.levelname]}{record.msg}{Style.RESET_ALL}"
        
        return super().format(record)

# Set up logging with custom formatter
def setup_logging(debug: bool = False):
    """Set up logging with custom formatting and handlers"""
    
    # Create logger
    logger = logging.getLogger("android_images")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Create console handler with custom formatter
    console_handler = logging.StreamHandler()
    console_formatter = ColoredFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # Create file handler with standard formatter
    file_handler = logging.FileHandler("android_images.log")
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

# Regex pattern for parsing version information
# Format examples:
# "12.0.0 (SQ1D.211205.016.A1, Dec 2021)"
# "7.1.1 (NMF26O, Dec 2016)"
# "15.0.0 (AP4A.250205.002)"
# "14.0.0 (AP2A.240505.004)"
# "6.0.1 (MMB29X)"
# "7.0.0 (NRD90M)"
# "7.1.2 (N2G47H, Apr 2017)"
# "7.1.0 (Europe, NDE63U, Nov 2016)"
# "7.1.0 (Verizon, NDE63X, Nov 2016)"
# "oreo-r6 (OPR6.170623.023, Nov 2017)"
# "7.1.1 (NMF26F, Dec 2016. All carriers except Verizon)"
# "14.0.0 (UD1A.230803.022.A3, Sep 2023, Verizon)"
# "14.0.0 (UD1A.230803.022.A4, Sep 2023, US-Emerging/G-store,CA,TW,AU,Fi)"
VERSION_PATTERN = re.compile(
    r"(?:[a-z-]+(?:\s+[a-z-]+)*\s+)?(\d+\.\d+\.\d+)\s\((?:(?:[A-Za-z]+(?:,\s+)?)*)?([A-Z0-9]+\.?\d*\.?\d*[A-Z0-9]*)(?:,\s(\d{1,2}\s+)?(\w+\s\w+)(?:,\s[^)]+)?)?\)"
)

# Additional pattern for modern Pixel devices
MODERN_PIXEL_PATTERN = re.compile(
    r"([a-z]+)-ota-([a-z0-9]+)\.([0-9]+)\.([0-9]+)(?:\.([a-z0-9]+))?-"
)

# Pattern for legacy builds (pre-Pixel era)
LEGACY_BUILD_PATTERN = re.compile(
    r"([a-z]+)-ota-([A-Z0-9]+)-([a-f0-9]+)\.zip"
)

# Pattern for factory images
FACTORY_IMAGE_PATTERN = re.compile(
    r"([a-z]+)-([a-z0-9]+\.\d+\.\d+\.?\d*[a-z0-9]*)-factory-[a-f0-9]+\.zip"
)

@dataclass
class AndroidImageInfo:
    """Class to store Android image information (OTA or factory)"""
    android_version: str
    build_version: str
    sub_version: Optional[str]
    release_date: str
    additional_info: Optional[str]
    download_url: str
    filename: str = field(init=False)
    last_checked: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    is_beta: bool = field(default=False)
    is_carrier: bool = field(default=False)
    is_factory: bool = field(default=False)
    is_region_specific: bool = field(default=False)
    region: Optional[str] = field(default=None)
    carrier: Optional[str] = field(default=None)
    build_type: str = field(default="stable")  # stable, beta, preview, qpr
    security_patch_level: Optional[str] = field(default=None)
    friendly_name: Optional[str] = field(default=None)  # Added friendly name field
    checksum: Optional[str] = field(default=None)  # Added checksum field

    def __post_init__(self):
        self.filename = self.download_url.split("/")[-1]
        # Enhanced image type detection
        self._detect_image_type()
        # Extract security patch level from build version
        self._extract_security_patch()
    
    def _detect_image_type(self):
        """Detect various image types and properties from filename and additional info"""
        filename_lower = self.filename.lower()
        info_lower = (self.additional_info or "").lower()
        
        # Basic type detection
        self.is_beta = "beta" in filename_lower or ".b" in self.build_version.lower()
        self.is_carrier = any(carrier in filename_lower or carrier in info_lower 
                            for carrier in ["tmobile", "verizon", "att", "sprint", "t-mobile", "at&t"])
        self.is_factory = "factory" in filename_lower
        self.is_region_specific = any(region in info_lower 
                                    for region in ["emea", "india", "japan", "korea", "china"])
        
        # Extract carrier information
        carrier_map = {
            "tmobile": "T-Mobile",
            "t-mobile": "T-Mobile",
            "verizon": "Verizon",
            "att": "AT&T",
            "at&t": "AT&T",
            "sprint": "Sprint"
        }
        for carrier_key, carrier_name in carrier_map.items():
            if carrier_key in filename_lower or carrier_key in info_lower:
                self.carrier = carrier_name
                break
        
        # Extract region information
        region_map = {
            "emea": "EMEA",
            "india": "India",
            "japan": "Japan",
            "korea": "Korea",
            "china": "China"
        }
        for region_key, region_name in region_map.items():
            if region_key in info_lower:
                self.region = region_name
                break
        
        # Determine build type
        if self.is_beta:
            self.build_type = "beta"
        elif "preview" in filename_lower or "preview" in info_lower:
            self.build_type = "preview"
        elif "qpr" in filename_lower or "qpr" in info_lower:
            self.build_type = "qpr"
        else:
            self.build_type = "stable"
    
    def _extract_security_patch(self):
        """Extract security patch level from build version"""
        # Build version format: AP4A.250205.002
        # Security patch is in the second part (250205)
        parts = self.build_version.split('.')
        if len(parts) >= 2:
            patch = parts[1]
            if len(patch) == 6:
                year = patch[:2]
                month = patch[2:4]
                self.security_patch_level = f"20{year}-{month}"
    
    def to_dict(self) -> Dict:
        return {
            "device": self.device,
            "android_version": self.android_version,
            "build_version": self.build_version,
            "sub_version": self.sub_version,
            "release_date": self.release_date,
            "additional_info": self.additional_info,
            "download_url": self.download_url,
            "filename": self.filename,
            "last_checked": self.last_checked,
            "is_beta": self.is_beta,
            "is_carrier": self.is_carrier,
            "is_factory": self.is_factory,
            "is_region_specific": self.is_region_specific,
            "region": self.region,
            "carrier": self.carrier,
            "build_type": self.build_type,
            "security_patch_level": self.security_patch_level
        }


class AndroidImageScraper:
    def __init__(self, 
                 url: str = "https://developers.google.com/android/ota", 
                 factory_url: str = "https://developers.google.com/android/images",
                 cache_file: str = "ota_cache.json",
                 factory_cache_file: str = "factory_cache.json",
                 cache_max_age_days: int = 1,
                 max_retries: int = 3,
                 retry_delay: float = 1.0,
                 rate_limit_delay: float = 2.0):
        """
        Initialize the Android image scraper.
        
        Args:
            url: URL of the Google OTA images page
            factory_url: URL of the Google Factory images page
            cache_file: File to store the previously scraped OTA data
            factory_cache_file: File to store the previously scraped factory image data
            cache_max_age_days: Maximum age of cache entries in days
            max_retries: Maximum number of retry attempts for failed requests
            retry_delay: Delay between retry attempts in seconds
            rate_limit_delay: Delay between successful requests in seconds
        """
        self.url = url
        self.factory_url = factory_url
        self.cache_file = cache_file
        self.factory_cache_file = factory_cache_file
        self.cache_max_age_days = cache_max_age_days
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",  # Do Not Track
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
        self.cookies = SimpleCookie()
        self.cookies["devsite_wall_acks"] = "nexus-image-tos,nexus-ota-tos"  # Combined TOS acknowledgments
        self.checksums = {}  # Cache for checksums
        
        # Device friendly names mapping
        self.device_names = {
            # Pixel 9 series
            'comet': 'Pixel 9 Pro Fold',
            'caiman': 'Pixel 9 Pro',
            'komodo': 'Pixel 9 Pro XL',
            'tokay': 'Pixel 9',
            
            # Pixel 8 series
            'husky': 'Pixel 8 Pro',
            'shiba': 'Pixel 8',
            'akita': 'Pixel 8a',
            
            # Pixel 7 series
            'cheetah': 'Pixel 7 Pro',
            'panther': 'Pixel 7',
            'lynx': 'Pixel 7a',
            
            # Pixel 6 series
            'raven': 'Pixel 6 Pro',
            'oriole': 'Pixel 6',
            'bluejay': 'Pixel 6a',
            
            # Pixel 5 series
            'redfin': 'Pixel 5',
            'barbet': 'Pixel 5a',
            
            # Pixel 4 series
            'coral': 'Pixel 4 XL',
            'flame': 'Pixel 4',
            'sunfish': 'Pixel 4a',
            'bramble': 'Pixel 4a 5G',
            
            # Pixel 3 series
            'crosshatch': 'Pixel 3 XL',
            'blueline': 'Pixel 3',
            'sargo': 'Pixel 3a XL',
            'bonito': 'Pixel 3a',
            
            # Pixel 2 series
            'taimen': 'Pixel 2 XL',
            'walleye': 'Pixel 2',
            
            # Pixel 1 series
            'marlin': 'Pixel XL',
            'sailfish': 'Pixel',
            
            # Special devices
            'felix': 'Pixel Fold',
            'tangorpro': 'Pixel Tablet',
            
            # Legacy devices
            'fugu': 'Nexus Player',
            'volantis': 'Nexus 9',
            'volantisg': 'Nexus 9 LTE',
            'razor': 'Nexus 6',
            'razorg': 'Nexus 6',
            'shamu': 'Nexus 6',
            'hammerhead': 'Nexus 5',
            'bullhead': 'Nexus 5X',
            'angler': 'Nexus 6P',
            'ryu': 'Nexus 6P'
        }
        
        # Device family mapping
        self.device_families = {
            'pixel9': ['comet', 'caiman', 'komodo', 'tokay'],  # Pixel 9 Pro Fold, Pro, Pro XL, and base
            'pixel8': ['husky', 'shiba', 'akita'],  # Pixel 8 Pro, base, and 8a
            'pixel7': ['cheetah', 'panther', 'lynx'],  # Pixel 7 Pro, base, and 7a
            'pixel6': ['raven', 'oriole', 'bluejay'],  # Pixel 6 Pro, base, and 6a
            'pixel5': ['redfin', 'barbet'],  # Pixel 5 and 5a
            'pixel4': ['coral', 'flame', 'sunfish', 'bramble'],  # Pixel 4 XL, base, 4a, and 4a 5G
            'pixel3': ['crosshatch', 'blueline', 'sargo', 'bonito'],  # Pixel 3 XL, base, 3a XL, and 3a
            'pixel2': ['taimen', 'walleye'],  # Pixel 2 XL and base
            'pixel1': ['marlin', 'sailfish'],  # Pixel XL and base
            'pixel_fold': ['felix'],  # Pixel Fold
            'pixel_tablet': ['tangorpro']  # Pixel Tablet Pro
        }
        
        # Reverse mapping for quick lookup
        self.device_to_family = {}
        for family, devices in self.device_families.items():
            for device in devices:
                self.device_to_family[device] = family
    
    def get_device_family(self, device_codename: str) -> Optional[str]:
        """Get the family name for a device codename."""
        return self.device_to_family.get(device_codename)
    
    def get_family_devices(self, family_name: str) -> List[str]:
        """Get all devices in a family."""
        return self.device_families.get(family_name, [])
    
    def get_latest_ota_for_family(self, family_name: str, **kwargs) -> Dict[str, Optional[AndroidImageInfo]]:
        """
        Get the latest OTA for all devices in a family.
        
        Args:
            family_name: Name of the device family
            **kwargs: Additional arguments to pass to get_latest_ota
            
        Returns:
            Dict mapping device codenames to their latest OTA info
        """
        devices = self.get_family_devices(family_name)
        if not devices:
            logger.error(f"No devices found in family: {family_name}")
            return {}
            
        results = {}
        for device in devices:
            results[device] = self.get_latest_ota(device, **kwargs)
            
        return results
    
    def get_cookie_dict(self) -> Dict[str, str]:
        """Convert cookie jar to dictionary for requests"""
        return {
            "devsite_wall_acks": "nexus-image-tos,nexus-ota-tos"
        }
        
    def save_page_cache(self, html_content: str, is_factory: bool = False) -> None:
        """Save the page content to cache file."""
        try:
            cache_file = self.factory_cache_file if is_factory else self.cache_file
            cache_data = {
                'timestamp': time.time(),
                'content': html_content
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            logger.debug(f"Page content cached successfully to {cache_file}")
        except Exception as e:
            logger.error(f"Failed to save page cache: {e}")

    def load_page_cache(self, is_factory: bool = False) -> Optional[str]:
        """Load the page content from cache if it exists and is not expired."""
        try:
            cache_file = self.factory_cache_file if is_factory else self.cache_file
            if not os.path.exists(cache_file):
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check if cache is expired
            if time.time() - cache_data['timestamp'] > self.cache_max_age_days * 24 * 3600:
                logger.debug(f"Cache expired for {cache_file}")
                return None
            
            logger.debug(f"Using cached page content from {cache_file}")
            return cache_data['content']
        except Exception as e:
            logger.error(f"Failed to load page cache: {e}")
            return None

    def fetch_page(self, url: Optional[str] = None, is_factory: bool = False) -> Optional[str]:
        """Fetch the page HTML content with rate limiting and retries."""
        # Use provided URL or default to appropriate URL based on type
        target_url = url or (self.factory_url if is_factory else self.url)
        
        # Try to load from cache first
        cached_content = self.load_page_cache(is_factory)
        if cached_content:
            return cached_content

        current_time = time.time()
        
        # Rate limiting
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last_request)
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Fetching page from {target_url}")
                response = requests.get(
                    target_url, 
                    headers=self.headers, 
                    cookies=self.get_cookie_dict(),
                    timeout=30
                )
                response.raise_for_status()
                self.last_request_time = time.time()
                
                # Save to appropriate cache
                self.save_page_cache(response.text, is_factory)
                return response.text
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Max retries reached, giving up")
                    return None
    
    def parse_version_text(self, text: str) -> Tuple:
        """Parse version text using regex pattern."""
        # First try the modern format
        match = VERSION_PATTERN.match(text)
        if match:
            groups = match.groups()
            # Make sure we have the expected number of groups even if some are None
            if len(groups) >= 2:
                android_version = groups[0]  # e.g., "15.0.0"
                build_version = groups[1]    # e.g., "BP1A.250305.019"
                
                # Extract release date from build version if available
                # Format: YYMMDD (e.g., 250305 for March 5th 2025)
                release_date = "Unknown"
                if len(build_version) >= 7:  # Ensure we have enough characters
                    try:
                        # Look for the date pattern in the build version
                        date_match = re.search(r'\.(\d{6})\.', build_version)
                        if date_match:
                            date_str = date_match.group(1)
                            year = int(date_str[:2])
                            month = int(date_str[2:4])
                            day = int(date_str[4:6])
                            
                            # Convert month number to month name
                            month_names = {
                                1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
                                5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
                                9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
                            }
                            month_name = month_names.get(month, 'Unknown')
                            
                            # Format the date with day
                            release_date = f"{day} {month_name} 20{year}"
                    except (ValueError, IndexError):
                        pass
                
                # If we couldn't get the date from build version, try the version text
                if release_date == "Unknown":
                    # Now we have two groups for the date: day (optional) and month+year
                    day = groups[2] if groups[2] else None
                    # Sometimes the date isn't in the expected format or is missing
                    if day:
                        release_date = f"{day} {groups[3]}" if groups[3] else "Unknown"
                    else:
                        release_date = groups[3] if groups[3] else "Unknown"
                
                additional_info = groups[4] if len(groups) > 4 and groups[4] else None
                
                return (android_version, build_version, None, release_date, additional_info)
        
        # Try legacy format with carrier (e.g., "4.4.2_r2 (Verizon) (KVT49L)")
        legacy_carrier_match = re.match(r'(\d+\.\d+(?:\.\d+)?(?:_r\d+)?)\s*\(([^)]+)\)\s*\(([A-Z0-9]+)\)', text)
        if legacy_carrier_match:
            android_version = legacy_carrier_match.group(1)
            carrier = legacy_carrier_match.group(2)
            build_version = legacy_carrier_match.group(3)
            return (android_version, build_version, None, "Unknown", carrier)
        
        # Try legacy format (e.g., "4.3 (JWR66Y)" or "2.3.7 (GWK74)")
        legacy_match = re.match(r'(\d+\.\d+(?:\.\d+)?)\s*\(([A-Z0-9]+)\)', text)
        if legacy_match:
            android_version = legacy_match.group(1)
            build_version = legacy_match.group(2)
            return (android_version, build_version, None, "Unknown", None)
        
        return None
    
    def parse_modern_pixel_filename(self, filename: str, parent_row=None) -> Optional[Tuple]:
        """Parse modern Pixel device filenames (e.g., husky-ota-bp1a.250305.019-b4977f37.zip)"""
        match = MODERN_PIXEL_PATTERN.match(filename)
        if not match:
            return None
            
        groups = match.groups()
        if len(groups) >= 4:
            device = groups[0]
            build_prefix = groups[1].upper()
            build_major = groups[2]
            build_minor = groups[3]
            build_variant = groups[4] if groups[4] else None
            
            # Determine Android version based on build prefix
            # For legacy devices (like Nexus Player), use the original build version
            if build_prefix.startswith('OPR'):
                # This is a legacy device build (like Nexus Player)
                build_version = f"{build_prefix}{build_major}{build_minor}"
                if build_variant:
                    build_version += f".{build_variant}"
                # For legacy devices, we need to parse the version from the parent row
                return None  # Return None to force legacy format parsing
            elif build_prefix.startswith(('BP', 'AP4')):
                android_version = "15.0.0"
            elif build_prefix.startswith('AP3'):
                android_version = "14.0.0"
            elif build_prefix.startswith('AP2'):
                android_version = "14.0.0"
            else:
                android_version = "13.0.0"  # fallback for older builds
            
            build_version = f"{build_prefix}{build_major}.{build_minor}"
            if build_variant:
                build_version += f".{build_variant}"
            
            # Try to get release date from parent row if available
            release_date = "Unknown"
            if parent_row:
                version_cell = parent_row.find('td')
                if version_cell:
                    version_text = version_cell.text.strip()
                    version_parts = self.parse_version_text(version_text)
                    if version_parts:
                        release_date = version_parts[3]  # Get release date from parsed version text
            
            return (android_version, build_version, None, release_date, None)
        
        return None
    
    def parse_legacy_build(self, filename: str) -> Optional[Tuple]:
        """Parse legacy build filenames (e.g., bullhead-ota-nmf26f-27b4075c.zip)"""
        match = LEGACY_BUILD_PATTERN.match(filename)
        if not match:
            return None
        
        groups = match.groups()
        if len(groups) >= 3:
            device = groups[0]
            build_version = groups[1]
            checksum = groups[2]
            
            # Determine Android version based on build version prefix
            if build_version.startswith('N2G'):
                android_version = "7.1.2"
            elif build_version.startswith('N4F'):
                android_version = "7.1.1"
    def get_version_sort_key(self, ota_info):
        """
        Create a sorting key for version comparison.
        This ensures variants like .b1, .d1 are sorted properly.
        """
        # Extract the major Android version (e.g., 14.0.0 -> 14)
        android_major = float(ota_info.android_version.split('.')[0])
        
        # Extract base build version and variant
        build_parts = ota_info.build_version.split('.')
        base_build = '.'.join(build_parts[:3])  # e.g., AP4A.250205.002
        
        # Determine if there's a variant code (like b1, a2, etc.)
        variant_priority = 0
        variant_number = 0
        
        if len(build_parts) > 3:
            variant = build_parts[3]
            # Set priority based on variant letter (a < b < c < d)
            variant_priority_map = {'a': 1, 'b': 2, 'c': 3, 'd': 4}
            for letter, priority in variant_priority_map.items():
                if variant.startswith(letter):
                    variant_priority = priority
                    break
                
            # Extract variant number if present
            if len(variant) > 1 and variant[1:].isdigit():
                variant_number = int(variant[1:])
        
        # Sort by:
        # 1. Android major version (e.g., 15, 14)
        # 2. Base build version (e.g., AP4A.250205.002)
        # 3. Build type priority (stable > qpr > preview > beta)
        # 4. Variant priority (a < b < c < d)
        # 5. Variant number (1, 2, 3, etc.)
        # 6. Image type (stable > carrier > region-specific)
        build_type_priority = {
            "stable": 0,
            "qpr": 1,
            "preview": 2,
            "beta": 3
        }.get(ota_info.build_type, 4)  # Default to lowest priority
        
        image_type_priority = 0
        if ota_info.is_carrier:
            image_type_priority = 1
        elif ota_info.is_region_specific:
            image_type_priority = 2
            
        return (android_major, base_build, build_type_priority, variant_priority, variant_number, image_type_priority)
    
    def parse_page(self, html: str, is_factory: bool = False) -> Dict[str, List[AndroidImageInfo]]:
        """
        Parse the HTML content to extract OTA image information.
        
        Args:
            html: HTML content to parse
            is_factory: Whether we're parsing factory images (affects column mapping)
            
        Returns:
            Dict containing device codenames as keys and lists of OTA images as values
        """
        if not html:
            logger.error("No HTML content provided to parse")
            return {}
            
        soup = BeautifulSoup(html, 'html.parser')
        result = {}
        
        # Create a mapping of download URLs to their checksums from the initial page
        checksum_map = {}
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 3:  # We need at least 3 columns for both factory and OTA images
                # For factory images:
                # td[1] = Version
                # td[2] = Flash Link (unused)
                # td[3] = Download Link
                # td[4] = SHA256 Checksum
                # For OTA images:
                # td[1] = Version
                # td[2] = Download Link
                # td[3] = SHA256 Checksum
                
                # Get the download link and checksum based on table structure
                if is_factory and len(cells) == 4:
                    # 4-column factory image table:
                    # td[1] = Version
                    # td[2] = Flash Link (unused)
                    # td[3] = Download Link
                    # td[4] = SHA256 Checksum
                    link = cells[2].find('a')  # Download link is in column 3
                    checksum = cells[3].text.strip()  # Checksum is in column 4
                else:
                    # For OTA images and 3-column factory images:
                    # td[1] = Version
                    # td[2] = Download Link
                    # td[3] = SHA256 Checksum
                    link = cells[1].find('a')  # Download link is in column 2
                    checksum = cells[2].text.strip()  # Checksum is in column 3
                
                if link and link.get('href'):
                    download_url = link['href']
                    # Normalize URL by removing any trailing slashes and converting to lowercase
                    normalized_url = download_url.rstrip('/').lower()
                    
                    # Try to extract a valid SHA256 hash from the checksum text
                    # This handles cases where .zip might be accidentally appended
                    sha256_match = re.search(r'^[a-fA-F0-9]{64}', checksum) if checksum else None
                    if sha256_match:
                        valid_checksum = sha256_match.group(0)
                        checksum_map[normalized_url] = valid_checksum
                        logger.debug(f"Found checksum for {download_url}: {valid_checksum}")
                    else:
                        logger.debug(f"Invalid or truncated checksum for {download_url}: {checksum}")
        
        # Log the total number of links found
        all_links = soup.find_all('a', href=lambda href: href and href.endswith('.zip'))
        logger.debug(f"Found {len(all_links)} total .zip links")
        
        # Find all links that end with .zip
        for link in all_links:
            download_url = link['href']
            # Normalize URL for checksum lookup
            normalized_url = download_url.rstrip('/').lower()
            filename = download_url.split('/')[-1]
            
            logger.debug(f"Processing link: {filename}")
            
            # Get the parent row for version text
            parent_row = link.find_parent('tr')
            
            # Try to find the device codename from the h2 element before the table
            device_codename = None
            table = parent_row.find_parent('table')
            if table:
                prev_h2 = table.find_previous('h2')
                if prev_h2 and prev_h2.get('id'):
                    device_codename = prev_h2['id']
                    logger.debug(f"Found device codename from h2: {device_codename}")
            
            # If we couldn't get the device codename from h2, try parsing from filename
            if not device_codename:
                # Try to parse modern Pixel device filenames first
                version_parts = self.parse_modern_pixel_filename(filename, parent_row)
                if version_parts:
                    device_codename = version_parts[0]
                else:
                    # Try to parse factory image format
                    if is_factory:
                        factory_match = FACTORY_IMAGE_PATTERN.match(filename)
                        if factory_match:
                            device_codename = factory_match.group(1)
                    else:
                        # Try to parse legacy format
                        device_match = re.search(r'([a-z]+)-ota-', filename)
                        if device_match:
                            device_codename = device_match.group(1)
            
            if not device_codename:
                logger.debug(f"Could not extract device codename from {filename}")
                continue
                
            # Try to parse modern Pixel device filenames first
            version_parts = self.parse_modern_pixel_filename(filename, parent_row)
            if version_parts:
                # Get checksum from our mapping using normalized URL
                checksum = checksum_map.get(normalized_url)
                if not checksum:
                    logger.warning(f"No checksum found for {download_url}")
                    
                ota_info = AndroidImageInfo(
                    android_version=version_parts[0],
                    build_version=version_parts[1],
                    sub_version=version_parts[2],
                    release_date=version_parts[3],
                    additional_info=version_parts[4],
                    download_url=download_url,
                    checksum=checksum,
                    is_factory=is_factory
                )
                
                if device_codename not in result:
                    result[device_codename] = []
                result[device_codename].append(ota_info)
                logger.debug(f"Added modern format {'factory image' if is_factory else 'OTA'} for {device_codename}: {ota_info.build_version}")
                continue
            
            # Try to parse factory image format
            if is_factory:
                factory_match = FACTORY_IMAGE_PATTERN.match(filename)
                if factory_match:
                    build_version = factory_match.group(2)
                    
                    # Get version text from parent row
                    version_text = None
                    if parent_row:
                        cells = parent_row.find_all('td')
                        if len(cells) >= 1:
                            version_text = cells[0].text.strip()
                    
                    # Parse version text to get Android version and other details
                    version_parts = self.parse_version_text(version_text) if version_text else None
                    if version_parts:
                        android_version = version_parts[0]
                        release_date = version_parts[3]
                        additional_info = version_parts[4]
                    else:
                        # Fallback to extracting Android version from build version
                        android_version = "14.0.0"  # Default for modern devices
                        if build_version.startswith('AP4'):
                            android_version = "15.0.0"
                        elif build_version.startswith('AP3'):
                            android_version = "15.0.0"
                        elif build_version.startswith('AP2'):
                            android_version = "14.0.0"
                        release_date = "Unknown"
                        additional_info = None
                    
                    # Get checksum from our mapping
                    checksum = checksum_map.get(normalized_url)
                    if not checksum:
                        logger.warning(f"No checksum found for {download_url}")
                    
                    ota_info = AndroidImageInfo(
                        android_version=android_version,
                        build_version=build_version,
                        sub_version=None,
                        release_date=release_date,
                        additional_info=additional_info,
                        download_url=download_url,
                        checksum=checksum,
                        is_factory=True
                    )
                    
                    if device_codename not in result:
                        result[device_codename] = []
                    result[device_codename].append(ota_info)
                    logger.debug(f"Added factory image for {device_codename}: {build_version}")
                    continue
            
            # Try to parse legacy format
            if not parent_row:
                logger.debug(f"No parent row found for {filename}")
                continue
                
            # For factory images, version is in td[1], for OTAs it's in td[1]
            cells = parent_row.find_all('td')
            if len(cells) < 3:  # We only need 3 columns minimum for both factory and OTA images
                logger.debug(f"Not enough cells in row for {filename} (found {len(cells)} cells)")
                continue
                
            # For factory images:
            # td[0] = Version
            # td[1] = Download Link
            # td[2] = SHA256 Checksum
            # For OTA images:
            # td[0] = Version
            # td[1] = Download Link
            # td[2] = SHA256 Checksum
            
            # Get the version cell based on table format
            if is_factory:
                if len(cells) == 4:
                    # 4-column factory image table:
                    # td[1] = Version
                    # td[2] = Flash Link (unused)
                    # td[3] = Download Link
                    # td[4] = SHA256 Checksum
                    version_cell = cells[1]  # Version is in first column
                    link = cells[2].find('a')  # Download link is in second column
                    checksum = cells[3].text.strip()  # Checksum is in third column
                else:
                    # 3-column factory image table:
                    # td[1] = Version
                    # td[2] = Download Link
                    # td[3] = SHA256 Checksum
                    version_cell = cells[0]  # Version is in first column
                    link = cells[2].find('a')  # Download link is in second column
                    checksum = cells[2].text.strip()  # Checksum is in third column
            else:
                # For OTA images (always 3 columns):
                # td[1] = Version
                # td[2] = Download Link
                # td[3] = SHA256 Checksum
                version_cell = cells[0]  # Version is always in first column
                
            if not version_cell:
                logger.debug(f"No version cell found for {filename}")
                continue
                
            version_text = version_cell.text.strip()
            version_parts = self.parse_version_text(version_text)
            
            if not version_parts:
                logger.debug(f"Could not parse version text: {version_text}")
                continue
                
            # Get checksum from our mapping using normalized URL
            checksum = checksum_map.get(normalized_url)
            if not checksum:
                logger.warning(f"No checksum found for {download_url}")
                
            # Create OTA info object
            ota_info = AndroidImageInfo(
                android_version=version_parts[0],
                build_version=version_parts[1],
                sub_version=version_parts[2],
                release_date=version_parts[3],
                additional_info=version_parts[4],
                download_url=download_url,
                checksum=checksum,
                is_factory=is_factory
            )
            
            if device_codename not in result:
                result[device_codename] = []
            result[device_codename].append(ota_info)
            logger.debug(f"Added legacy format {'factory image' if is_factory else 'OTA'} for {device_codename}: {ota_info.build_version}")
        
        # Sort each device's OTAs by our custom sorting function (newest first)
        for device in result:
            result[device].sort(key=self.get_version_sort_key, reverse=True)
        
        return result
    
    def fetch_checksum(self, download_url: str) -> Optional[str]:
        """
        Get the checksum from the cached mapping.
        
        Args:
            download_url: URL of the OTA file
            
        Returns:
            The checksum if found, None otherwise
        """
        # Check cache first
        if download_url in self.checksums:
            logger.debug(f"Found checksum in cache for {download_url}: {self.checksums[download_url]}")
            return self.checksums[download_url]
            
        logger.warning(f"No checksum found for {download_url}")
        return None
    
    def validate_cache(self) -> bool:
        """
        Validate the cache file and its contents.
        
        Returns:
            bool: True if cache is valid, False otherwise
        """
        try:
            if not os.path.exists(self.cache_file):
                return False
                
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Check if data is a dictionary
            if not isinstance(data, dict):
                return False
                
            # Check each device's entries
            for device, entries in data.items():
                if not isinstance(entries, list):
                    return False
                    
                for entry in entries:
                    # Check required fields
                    required_fields = {
                        'device', 'android_version', 'build_version',
                        'release_date', 'download_url', 'filename',
                        'last_checked'
                    }
                    if not all(field in entry for field in required_fields):
                        return False
                        
            return True
        except Exception as e:
            logger.error(f"Cache validation error: {e}")
            return False
    
    def cleanup_cache(self) -> None:
        """
        Clean up old entries from the cache.
        """
        try:
            if not os.path.exists(self.cache_file):
                return
                
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            current_time = datetime.datetime.now()
            max_age = datetime.timedelta(days=self.cache_max_age_days)
            
            # Clean up each device's entries
            for device in list(data.keys()):
                entries = data[device]
                valid_entries = []
                
                for entry in entries:
                    last_checked = datetime.datetime.fromisoformat(entry['last_checked'])
                    if current_time - last_checked <= max_age:
                        valid_entries.append(entry)
                
                if valid_entries:
                    data[device] = valid_entries
                else:
                    del data[device]
            
            # Save cleaned up data
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
            logger.info("Cache cleanup completed")
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")
    
    def load_cache(self) -> Dict:
        """Load cached OTA data from file."""
        try:
            if os.path.exists(self.cache_file):
                # Validate cache before loading
                if not self.validate_cache():
                    logger.warning("Cache validation failed, creating new cache")
                    return {}
                    
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert loaded data back to OTAInfo objects
                    for device in data:
                        data[device] = [AndroidImageInfo(**ota) for ota in data[device]]
                    return data
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
        return {}
    
    def save_cache(self, data: Dict) -> None:
        """Save OTA data to cache file."""
        try:
            # Convert OTAInfo objects to dictionaries before saving
            cache_data = {}
            for device in data:
                cache_data[device] = [ota.to_dict() for ota in data[device]]
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def find_new_images(self, old_data: Dict, new_data: Dict) -> Dict[str, List[AndroidImageInfo]]:
        """Find new OTA images by comparing old and new data."""
        new_images = {}
        
        for device, new_otas in new_data.items():
            if device not in old_data:
                new_images[device] = new_otas
                continue
                
            old_otas = old_data[device]
            new_device_otas = []
            
            for new_ota in new_otas:
                # Check if this OTA is new or has been updated
                is_new = True
                for old_ota in old_otas:
                    if (new_ota.android_version == old_ota.android_version and 
                        new_ota.build_version == old_ota.build_version):
                        is_new = False
                        break
                
                if is_new:
                    new_device_otas.append(new_ota)
            
            if new_device_otas:
                new_images[device] = new_device_otas
        
        return new_images
    
    def run(self) -> Dict[str, List[AndroidImageInfo]]:
        """
        Run the scraper and return any new images found.
        
        Returns:
            Dict containing device codenames as keys and lists of new images as values
        """
        # Clean up old cache entries
        self.cleanup_cache()
        
        # Load previous data
        old_data = self.load_cache()
        
        # Fetch and parse page
        html = self.fetch_page()
        if not html:
            logger.error("Failed to fetch page, aborting")
            return {}
        
        # Parse the page
        new_data = self.parse_page(html)
        
        # Save the new data
        self.save_cache(new_data)
        
        # Find new images
        new_images = self.find_new_images(old_data, new_data)
        
        return new_images
    
    def get_latest_ota(self, device_codename: str, 
                      include_beta: bool = False,
                      prefer_stable: bool = True,
                      include_carrier: bool = False,
                      include_region_specific: bool = False,
                      prefer_factory_images: bool = False,
                      carrier: Optional[str] = None,
                      region: Optional[str] = None,
                      specific_build: Optional[str] = None) -> Optional[AndroidImageInfo]:
        """
        Get the latest OTA for a specific device with filtering options.
        
        Args:
            device_codename: Device codename to check
            include_beta: Whether to include beta builds (default: False)
            prefer_stable: Prefer stable builds over beta if available (default: True)
            include_carrier: Whether to include carrier-specific builds (default: False)
            include_region_specific: Whether to include region-specific builds (default: False)
            prefer_factory_images: Prefer factory images over OTAs if available (default: False)
            carrier: Specific carrier to filter for (e.g., "T-Mobile", "Verizon")
            region: Specific region to filter for (e.g., "EMEA", "India")
            specific_build: Specific build number to look for (e.g., "BP1A.250305.019")
            
        Returns:
            Latest OTA info or None if not found
        """
        # Fetch and parse page
        html = self.fetch_page()
        if not html:
            logger.error("Failed to fetch page, aborting")
            return None
        
        # Parse the page
        data = self.parse_page(html)
        
        # First try exact match
        if device_codename in data and data[device_codename]:
            logger.info(f"Found {len(data[device_codename])} OTAs for device: {device_codename}")
            matching_otas = data[device_codename]
        else:
            # If not found, try to find rows that contain the device codename in download URLs
            soup = BeautifulSoup(html, 'html.parser')
            matching_otas = []
            
            # Build the search pattern for the device in the link
            link_pattern = f"{device_codename}-ota-"
            
            # Find all links that contain the device name
            for link in soup.find_all('a', href=lambda href: href and link_pattern in href.lower() and href.endswith('.zip')):
                download_url = link['href']
                filename = download_url.split('/')[-1]
                
                # Get the parent row for version text
                parent_row = link.find_parent('tr')
                
                # Try to parse modern Pixel device filenames first
                version_parts = self.parse_modern_pixel_filename(filename, parent_row)
                if version_parts:
                    # Get checksum from the table
                    checksum = None
                    if parent_row:
                        cells = parent_row.find_all('td')
                        if len(cells) >= 3:
                            checksum_text = cells[2].text.strip()
                            sha256_match = re.search(r'^[a-fA-F0-9]{64}', checksum_text)
                            if sha256_match:
                                checksum = sha256_match.group(0)
                                logger.debug(f"Found checksum for {download_url}: {checksum}")
                    
                    ota_info = AndroidImageInfo(
                        android_version=version_parts[0],
                        build_version=version_parts[1],
                        sub_version=version_parts[2],
                        release_date=version_parts[3],
                        additional_info=version_parts[4],
                        download_url=download_url,
                        checksum=checksum
                    )
                    matching_otas.append(ota_info)
                    continue
                
                # Try to parse legacy format
                parent_row = link.find_parent('tr')
                if not parent_row:
                    continue
                    
                version_cell = parent_row.find('td')
                if not version_cell:
                    continue
                    
                version_text = version_cell.text.strip()
                version_parts = self.parse_version_text(version_text)
                
                if not version_parts:
                    continue
                
                # Get checksum from the table
                cells = parent_row.find_all('td')
                checksum = None
                if len(cells) >= 3:
                    checksum_text = cells[2].text.strip()
                    sha256_match = re.search(r'^[a-fA-F0-9]{64}', checksum_text)
                    if sha256_match:
                        checksum = sha256_match.group(0)
                        logger.debug(f"Found checksum for {download_url}: {checksum}")
                
                ota_info = AndroidImageInfo(
                    android_version=version_parts[0],
                    build_version=version_parts[1],
                    sub_version=version_parts[2],
                    release_date=version_parts[3],
                    additional_info=version_parts[4],
                    download_url=download_url,
                    checksum=checksum
                )
                
                matching_otas.append(ota_info)
        
        if not matching_otas:
            logger.error(f"No OTAs found for device: {device_codename}")
            return None
            
        logger.info(f"Found {len(matching_otas)} OTAs for device {device_codename}")
        
        # Filter OTAs based on user preferences
        filtered_otas = matching_otas
        
        # Filter by specific build if requested
        if specific_build:
            filtered_otas = [ota for ota in filtered_otas if ota.build_version == specific_build]
            if not filtered_otas:
                logger.error(f"No OTA found with build number: {specific_build}")
                return None
            logger.info(f"Found OTA with specific build number: {specific_build}")
        
        # Filter out beta builds if not included
        if not include_beta:
            filtered_otas = [ota for ota in filtered_otas if not ota.is_beta]
            logger.info(f"Filtered out beta builds. Remaining: {len(filtered_otas)}")
        
        # Filter out carrier-specific builds if not included
        if not include_carrier:
            filtered_otas = [ota for ota in filtered_otas if not ota.is_carrier]
            logger.info(f"Filtered out carrier builds. Remaining: {len(filtered_otas)}")
        
        # Filter out region-specific builds if not included
        if not include_region_specific:
            filtered_otas = [ota for ota in filtered_otas if not ota.is_region_specific]
            logger.info(f"Filtered out region-specific builds. Remaining: {len(filtered_otas)}")
        
        # Filter by specific carrier if requested
        if carrier:
            filtered_otas = [ota for ota in filtered_otas if ota.carrier == carrier]
            logger.info(f"Filtered for carrier {carrier}. Remaining: {len(filtered_otas)}")
        
        # Filter by specific region if requested
        if region:
            filtered_otas = [ota for ota in filtered_otas if ota.region == region]
            logger.info(f"Filtered for region {region}. Remaining: {len(filtered_otas)}")
        
        if not filtered_otas:
            logger.error(f"No matching OTAs found for device {device_codename} after filtering")
            return None
        
        # Sort all OTAs by version
        all_sorted_otas = sorted(
            filtered_otas, 
            key=self.get_version_sort_key, 
            reverse=True
        )
        
        # If prefer_stable is True, try to find the newest stable version first
        if prefer_stable:
            stable_otas = [ota for ota in all_sorted_otas if ota.build_type == "stable"]
            
            if stable_otas:
                logger.info(f"Using stable build for {device_codename}: {stable_otas[0].build_version}")
                if stable_otas[0].checksum:
                    logger.info(f"Found checksum for stable build: {stable_otas[0].checksum}")
                return stable_otas[0]
        
        # Either prefer_stable is False or no stable builds found
        logger.info(f"Using build for {device_codename}: {all_sorted_otas[0].build_version}")
        if all_sorted_otas[0].checksum:
            logger.info(f"Found checksum for build: {all_sorted_otas[0].checksum}")
        return all_sorted_otas[0]
    
    def analyze_family_update_status(self, family_name: str, **kwargs) -> Dict:
        """
        Analyze update status for all devices in a family.
        
        Args:
            family_name: Name of the device family
            **kwargs: Additional arguments to pass to get_latest_ota
            
        Returns:
            Dict containing analysis results
        """
        results = self.get_latest_ota_for_family(family_name, **kwargs)
        
        if not results:
            return {
                'family': family_name,
                'status': 'error',
                'message': f'No devices found in family: {family_name}',
                'devices': {}
            }
        
        # Group devices by Android version and build version
        version_groups = {}
        for device, ota in results.items():
            if not ota:
                continue
                
            key = (ota.android_version, ota.build_version)
            if key not in version_groups:
                version_groups[key] = []
            version_groups[key].append(device)
        
        # Find the most common version
        if version_groups:
            most_common = max(version_groups.items(), key=lambda x: len(x[1]))
            android_version, build_version = most_common[0]
            devices = most_common[1]
            
            # Check if all devices are on the same version
            all_devices = set(results.keys())
            devices_on_version = set(devices)
            missing_devices = all_devices - devices_on_version
            
            return {
                'family': family_name,
                'status': 'complete' if not missing_devices else 'partial',
                'android_version': android_version,
                'build_version': build_version,
                'devices_on_version': list(devices_on_version),
                'missing_devices': list(missing_devices),
                'all_devices': list(all_devices),
                'version_groups': {
                    f"{v[0]} ({v[1]})": d for v, d in version_groups.items()
                }
            }
        else:
            return {
                'family': family_name,
                'status': 'error',
                'message': 'No valid OTAs found for any devices in family',
                'devices': results
            }
    
    def get_cache_statistics(self) -> Dict:
        """
        Get statistics about the cache.
        
        Returns:
            Dict containing cache statistics
        """
        if not os.path.exists(self.cache_file):
            return {
                "status": "error",
                "message": "Cache file does not exist",
                "total_entries": 0,
                "total_size_bytes": 0,
                "last_modified": None,
                "devices": {},
                "families": {}
            }
            
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            total_entries = sum(len(entries) for entries in cache_data.values())
            total_size_bytes = os.path.getsize(self.cache_file)
            last_modified = datetime.fromtimestamp(os.path.getmtime(self.cache_file))
            
            # Count entries by device
            devices = {}
            for build_id, entries in cache_data.items():
                for entry in entries:
                    device = entry.get('device')
                    if device:
                        if device not in devices:
                            devices[device] = 0
                        devices[device] += 1
            
            # Count entries by family
            families = {}
            for device, count in devices.items():
                family = self.get_device_family(device)
                if family:
                    if family not in families:
                        families[family] = 0
                    families[family] += count
            
            return {
                "status": "success",
                "total_entries": total_entries,
                "total_size_bytes": total_size_bytes,
                "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
                "last_modified": last_modified.isoformat(),
                "devices": devices,
                "families": families
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "total_entries": 0,
                "total_size_bytes": 0,
                "last_modified": None,
                "devices": {},
                "families": {}
            }
    
    def clear_cache(self) -> bool:
        """
        Clear the cache file.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
                logger.info("Cache file cleared successfully")
                return True
            else:
                logger.warning("Cache file does not exist")
                return False
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False

    def get_latest_factory_image(self, device_codename: str, **kwargs) -> Optional[AndroidImageInfo]:
        """
        Get the latest factory image for a specific device.
        
        Args:
            device_codename: Device codename to check
            **kwargs: Additional arguments for filtering
            
        Returns:
            Latest factory image info or None if not found
        """
        # Fetch and parse factory images page
        html = self.fetch_page(self.factory_url, is_factory=True)
        if not html:
            logger.error("Failed to fetch factory images page, aborting")
            return None
        
        # Parse the page with is_factory=True to use correct column mapping
        data = self.parse_page(html, is_factory=True)
        
        if device_codename in data and data[device_codename]:
            logger.info(f"Found {len(data[device_codename])} factory images for device: {device_codename}")
            matching_images = data[device_codename]
        else:
            logger.error(f"No factory images found for device: {device_codename}")
            return None
            
        logger.info(f"Found {len(matching_images)} factory images for device {device_codename}")
        
        # Sort by version and return the latest
        all_sorted_images = sorted(
            matching_images,
            key=self.get_version_sort_key,
            reverse=True
        )
        
        return all_sorted_images[0]


def print_security_warning(message: str):
    """Print a prominent security warning message"""
    if is_interactive_terminal():
        print(f"\n{Fore.RED}{Back.WHITE}{'!' * 80}{Style.RESET_ALL}")
        print(f"{Fore.RED}{Back.WHITE}SECURITY WARNING: {message}{Style.RESET_ALL}")
        print(f"{Fore.RED}{Back.WHITE}{'!' * 80}{Style.RESET_ALL}\n")
    else:
        print(f"\n{'!' * 80}")
        print(f"SECURITY WARNING: {message}")
        print(f"{'!' * 80}\n")

def verify_file_hash(file_path: str, expected_hash: str) -> bool:
    """
    Verify the hash of an existing file.
    
    Args:
        file_path: Path to the file to verify
        expected_hash: Expected hash value (can be full SHA256 or shortened version)
        
    Returns:
        bool: True if hash matches, False otherwise
    """
    try:
        print_info(f"Verifying SHA256 hash for {os.path.basename(file_path)}...")
        
        block_size = 8192  # 8 KB chunks
        
        # Initialize SHA256 hash object (Google uses SHA256 for OTA files)
        hash_obj = hashlib.sha256()
        
        # Get file size for progress calculation
        file_size = os.path.getsize(file_path)
        processed = 0
        
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(block_size)
                if not data:
                    break
                hash_obj.update(data)
                processed += len(data)
                
                # Show progress for interactive terminals
                if is_interactive_terminal():
                    percent = int(100 * processed / file_size)
                    sys.stdout.write(f"\r{Fore.CYAN}Verifying:{Style.RESET_ALL} {percent}% ({processed}/{file_size} bytes)")
                    sys.stdout.flush()
        
        if is_interactive_terminal():
            print()  # New line after progress bar
        
        actual_hash = hash_obj.hexdigest()
        
        # If the expected hash is 8 characters, it's a shortened version
        if len(expected_hash) == 8:
            if actual_hash.startswith(expected_hash):
                return True
            print_error(f"Hash mismatch for {os.path.basename(file_path)}:")
            print_error(f"  Expected (short): {expected_hash}")
            print_error(f"  Actual (short):   {actual_hash[:8]}")
            return False
        # If it's 64 characters, it's the full SHA256 hash
        elif len(expected_hash) == 64:
            if actual_hash == expected_hash:
                return True
            print_error(f"Hash mismatch for {os.path.basename(file_path)}:")
            print_error(f"  Expected: {expected_hash}")
            print_error(f"  Actual:   {actual_hash}")
            return False
        else:
            print_security_warning(f"Unsupported hash length: {len(expected_hash)}. File integrity cannot be verified!")
            return False
            
    except Exception as e:
        print_security_warning(f"Error verifying file hash: {e}. File integrity cannot be verified!")
        return False

def download_with_progress(url: str, output_file: str, verify_hash: bool = True, expected_hash: Optional[str] = None) -> bool:
    """Download a file with progress bar and optional hash verification"""
    try:
        # Check if file exists and verify hash if needed
        if os.path.exists(output_file):
            if expected_hash and len(expected_hash) == 64:  # Only verify if we have a full SHA256 hash
                if verify_file_hash(output_file, expected_hash):
                    print_success(f"File exists and hash verified: {os.path.basename(output_file)}")
                    return True
                else:
                    print_warning(f"File exists but hash mismatch, will re-download: {os.path.basename(output_file)}")
                    os.remove(output_file)
            else:
                print_security_warning(f"File exists but no valid hash provided for verification: {os.path.basename(output_file)}")
                return True

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Get file size
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded = 0

        # Download with progress bar
        with open(output_file, 'wb') as f:
            for data in response.iter_content(block_size):
                downloaded += len(data)
                f.write(data)
                if total_size:
                    percent = int(100 * downloaded / total_size)
                    print_download_progress(percent, downloaded, total_size)

        print()  # New line after progress bar

        # Always verify hash after download if we have a full SHA256 hash
        if expected_hash and len(expected_hash) == 64:
            if verify_file_hash(output_file, expected_hash):
                print_success(f"Download completed and hash verified: {os.path.basename(output_file)}")
                return True
            else:
                print_error(f"Hash verification failed: {os.path.basename(output_file)}")
                # Clean up the file since verification failed
                try:
                    os.remove(output_file)
                    print_info(f"Removed file due to hash verification failure: {os.path.basename(output_file)}")
                except Exception as e:
                    print_error(f"Failed to remove file after hash verification failure: {e}")
                return False

        print_success(f"Download completed: {os.path.basename(output_file)}")
        return True

    except Exception as e:
        print_error(f"Error downloading file: {str(e)}")
        # Clean up the file if it exists and there was an error
        try:
            if os.path.exists(output_file):
                os.remove(output_file)
                print_info(f"Removed file due to download error: {os.path.basename(output_file)}")
        except Exception as cleanup_error:
            print_error(f"Failed to remove file after download error: {cleanup_error}")
        return False

def is_interactive_terminal() -> bool:
    """
    Check if the script is running in an interactive terminal session.
    
    Returns:
        bool: True if running in an interactive terminal, False if running via cron or non-interactive
    """
    try:
        # Check if --non-interactive flag is set
        if hasattr(sys, 'argv') and '--non-interactive' in sys.argv:
            return False
            
        # Check if stdout is connected to a terminal
        if not sys.stdout.isatty():
            return False
            
        # Check if running in a cron job or being called by another script
        if 'CRON' in os.environ or 'CRON_TZ' in os.environ:
            return False
            
        # Check if parent process is a shell script or cron
        try:
            import psutil
            parent = psutil.Process().parent()
            if parent:
                parent_name = parent.name().lower()
                if any(x in parent_name for x in ['cron', 'sh', 'bash', 'zsh', 'fish']):
                    return False
        except (ImportError, psutil.NoSuchProcess):
            pass
            
        return True
    except:
        return False

def print_section_header(title: str):
    """Print a formatted section header"""
    if not is_interactive_terminal():
        print(f"\n=== {title} ===\n")
        return
        
    width = 80
    padding = (width - len(title) - 4) // 2
    print(f"\n{Fore.CYAN}{'=' * width}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * padding} {title} {'=' * padding}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * width}{Style.RESET_ALL}\n")

def print_device_info(device: str, ota: AndroidImageInfo, scraper: AndroidImageScraper):
    """Print formatted device information"""
    friendly_name = scraper.device_names.get(device, device)
    print_section_header(f"Device Information: {friendly_name}")
    
    if is_interactive_terminal():
        info_lines = [
            f"{Fore.GREEN}Device Codename:{Style.RESET_ALL} {device}",
            f"{Fore.GREEN}Friendly Name:{Style.RESET_ALL} {friendly_name}",
            f"{Fore.GREEN}Android Version:{Style.RESET_ALL} {ota.android_version}",
            f"{Fore.GREEN}Build Version:{Style.RESET_ALL} {ota.build_version}",
            f"{Fore.GREEN}Release Date:{Style.RESET_ALL} {ota.release_date}",
            f"{Fore.GREEN}Build Type:{Style.RESET_ALL} {ota.build_type.title()}",
            f"{Fore.GREEN}Download URL:{Style.RESET_ALL} {ota.download_url}"
        ]
        
        if ota.security_patch_level:
            info_lines.append(f"{Fore.GREEN}Security Patch:{Style.RESET_ALL} {ota.security_patch_level}")
        if ota.carrier:
            info_lines.append(f"{Fore.GREEN}Carrier:{Style.RESET_ALL} {ota.carrier}")
        if ota.region:
            info_lines.append(f"{Fore.GREEN}Region:{Style.RESET_ALL} {ota.region}")
        if ota.checksum:
            info_lines.append(f"{Fore.GREEN}Checksum:{Style.RESET_ALL} {ota.checksum}")
    else:
        info_lines = [
            f"Device Codename: {device}",
            f"Friendly Name: {friendly_name}",
            f"Android Version: {ota.android_version}",
            f"Build Version: {ota.build_version}",
            f"Release Date: {ota.release_date}",
            f"Build Type: {ota.build_type.title()}",
            f"Download URL: {ota.download_url}"
        ]
        
        if ota.security_patch_level:
            info_lines.append(f"Security Patch: {ota.security_patch_level}")
        if ota.carrier:
            info_lines.append(f"Carrier: {ota.carrier}")
        if ota.region:
            info_lines.append(f"Region: {ota.region}")
        if ota.checksum:
            info_lines.append(f"Checksum: {ota.checksum}")
    
    print("\n".join(info_lines))
    print()

def print_download_progress(percent: int, downloaded: int, total: int):
    """Print formatted download progress"""
    if not is_interactive_terminal():
        if percent % 10 == 0:  # Only print every 10% in non-interactive mode
            print(f"Download progress: {percent}% ({downloaded}/{total} bytes)")
        return
        
    bar_width = 50
    filled = int(bar_width * percent / 100)
    bar = f"{Fore.GREEN}{'=' * filled}{Style.RESET_ALL}{' ' * (bar_width - filled)}"
    sys.stdout.write(f"\r{Fore.CYAN}Downloading:{Style.RESET_ALL} [{bar}] {percent}% ({downloaded}/{total} bytes)")
    sys.stdout.flush()

def print_success(message: str):
    """Print a success message"""
    if is_interactive_terminal():
        print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")
    else:
        print(f"[SUCCESS] {message}")

def print_error(message: str):
    """Print an error message"""
    if is_interactive_terminal():
        print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")
    else:
        print(f"[ERROR] {message}")

def print_warning(message: str):
    """Print a warning message"""
    if is_interactive_terminal():
        print(f"{Fore.YELLOW}! {message}{Style.RESET_ALL}")
    else:
        print(f"[WARNING] {message}")

def print_info(message: str):
    """Print an info message"""
    if is_interactive_terminal():
        print(f"{Fore.CYAN}ℹ {message}{Style.RESET_ALL}")
    else:
        print(f"[INFO] {message}")

def main():
    """Main function to run the scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Google Android OTA and Factory Image Scraper")
    parser.add_argument("--device", "-d", type=str, help="Device codename to check")
    parser.add_argument("--family", "-f", type=str, help="Device family to check (e.g., pixel8, pixel7)")
    parser.add_argument("--check-all", "-a", action="store_true", help="Check for all new OTA images")
    parser.add_argument("--include-beta", action="store_true", help="Include beta builds (excluded by default)")
    parser.add_argument("--include-carrier", action="store_true", help="Include carrier-specific builds (excluded by default)")
    parser.add_argument("--include-region", action="store_true", help="Include region-specific builds (excluded by default)")
    parser.add_argument("--no-stable-preference", action="store_true", help="Don't prefer stable builds over beta")
    parser.add_argument("--carrier", type=str, help="Filter for specific carrier (e.g., T-Mobile, Verizon)")
    parser.add_argument("--region", type=str, help="Filter for specific region (e.g., EMEA, India)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--save-html", action="store_true", help="Save the fetched HTML to a file for debugging")
    parser.add_argument("--output", "-o", type=str, help="Download the OTA image to the specified file")
    parser.add_argument("--show-security-patch", action="store_true", help="Show security patch level for each build")
    parser.add_argument("--list-devices", action="store_true", help="List all available devices with their friendly names")
    parser.add_argument("--list-families", action="store_true", help="List all available device families")
    parser.add_argument("--no-verify-hash", action="store_true", help="Skip hash verification of downloaded files")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum number of retry attempts for failed requests")
    parser.add_argument("--retry-delay", type=float, default=1.0, help="Delay between retry attempts in seconds")
    parser.add_argument("--rate-limit-delay", type=float, default=2.0, help="Delay between successful requests in seconds")
    parser.add_argument("--analyze-family", action="store_true", help="Analyze update status for a device family")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache statistics")
    parser.add_argument("--clear-cache", action="store_true", help="Clear the cache file")
    parser.add_argument("--factory", action="store_true", help="Download factory image instead of OTA")
    parser.add_argument("--factory-url", type=str, help="Custom URL for factory images page")
    parser.add_argument("--build", "-b", type=str, nargs="?", const="", help="Specific build number to download (e.g., BP1A.250305.019). If empty, shows interactive build picker.")
    parser.add_argument("--non-interactive", action="store_true", help="Force non-interactive mode even in interactive terminal sessions")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.debug:
        logger = setup_logging(debug=True)
        print_info("Debug logging enabled")
    
    print_section_header("Google Android OTA and Factory Image Scraper")
    
    # Initialize scraper with factory URL if provided
    scraper = AndroidImageScraper(
        factory_url=args.factory_url if args.factory_url else "https://developers.google.com/android/images",
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        rate_limit_delay=args.rate_limit_delay
    )
    print_info("Starting Android image scraper")
    
    # Save HTML for debugging if requested
    if args.save_html:
        print_info("Fetching HTML content...")
        html = scraper.fetch_page()
        if html:
            with open("ota_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            print_success("Saved HTML content to ota_page.html")
        else:
            print_error("Failed to fetch HTML content")
            return
    
    # Get latest image for a specific device
    if args.device:
        device = args.device.lower()
        print_info(f"Checking latest {'factory image' if args.factory else 'OTA'} for device: {device}")
        
        # Determine filter settings based on command-line arguments
        include_beta = args.include_beta
        prefer_stable = not args.no_stable_preference
        include_carrier = args.include_carrier
        include_region_specific = args.include_region
        
        print_info("Filter settings:")
        print_info(f"  • Include beta: {include_beta}")
        print_info(f"  • Prefer stable: {prefer_stable}")
        print_info(f"  • Include carrier: {include_carrier}")
        print_info(f"  • Include region-specific: {include_region_specific}")
        
        if args.carrier:
            print_info(f"  • Filtering for carrier: {args.carrier}")
        if args.region:
            print_info(f"  • Filtering for region: {args.region}")
        
        # Get the appropriate image based on factory flag
        if args.factory:
            # If build argument is empty and we're in an interactive session, show available builds
            if args.build == "" and is_interactive_terminal():
                print_info("Fetching available factory images...")
                html = scraper.fetch_page(scraper.factory_url, is_factory=True)
                if html:
                    data = scraper.parse_page(html, is_factory=True)
                    if device in data and data[device]:
                        # Apply the same filters as the main OTA selection
                        filtered_otas = data[device]
                        
                        # Filter out beta builds if not included
                        if not args.include_beta:
                            filtered_otas = [ota for ota in filtered_otas if not ota.is_beta]
                            print_info(f"Filtered out beta builds. Remaining: {len(filtered_otas)}")
                        
                        # Filter out carrier-specific builds if not included
                        if not args.include_carrier:
                            filtered_otas = [ota for ota in filtered_otas if not ota.is_carrier]
                            print_info(f"Filtered out carrier builds. Remaining: {len(filtered_otas)}")
                        
                        # Filter out region-specific builds if not included
                        if not args.include_region:
                            filtered_otas = [ota for ota in filtered_otas if not ota.is_region_specific]
                            print_info(f"Filtered out region-specific builds. Remaining: {len(filtered_otas)}")
                        
                        # Filter by specific carrier if requested
                        if args.carrier:
                            filtered_otas = [ota for ota in filtered_otas if ota.carrier == args.carrier]
                            print_info(f"Filtered for carrier {args.carrier}. Remaining: {len(filtered_otas)}")
                        
                        # Filter by specific region if requested
                        if args.region:
                            filtered_otas = [ota for ota in filtered_otas if ota.region == args.region]
                            print_info(f"Filtered for region {args.region}. Remaining: {len(filtered_otas)}")
                        
                        if not filtered_otas:
                            print_error(f"No matching builds found for device {device} after filtering")
                            return
                        
                        print_section_header(f"Available builds for {scraper.device_names.get(device, device)}")
                        
                        # Show active filters
                        print_info("Active filters:")
                        filter_lines = []
                        if not args.include_beta:
                            filter_lines.append("  • Beta builds excluded")
                        if not args.include_carrier:
                            filter_lines.append("  • Carrier-specific builds excluded")
                        if not args.include_region:
                            filter_lines.append("  • Region-specific builds excluded")
                        if args.carrier:
                            filter_lines.append(f"  • Only showing builds for carrier: {args.carrier}")
                        if args.region:
                            filter_lines.append(f"  • Only showing builds for region: {args.region}")
                        if not filter_lines:
                            filter_lines.append("  • No filters applied (showing all builds)")
                        print("\n".join(filter_lines))
                        print()
                        
                        print_info("Available builds (sorted by date):")
                        for idx, ota in enumerate(filtered_otas, 1):
                            build_info = f"{idx}. Android {ota.android_version} ({ota.build_version})"
                            if ota.release_date != "Unknown":
                                build_info += f" - {ota.release_date}"
                            if ota.is_beta:
                                build_info += " [Beta]"
                            if ota.is_carrier:
                                build_info += f" [{ota.carrier}]"
                            if ota.is_region_specific:
                                build_info += f" [{ota.region}]"
                            print(build_info)
                        
                        try:
                            choice = input("\nEnter the number of the build to download (or press Enter to cancel): ").strip()
                            if choice.isdigit() and 1 <= int(choice) <= len(filtered_otas):
                                selected_ota = filtered_otas[int(choice)-1]
                                print_device_info(device, selected_ota, scraper)
                                
                                # Download if output file specified
                                if args.output:
                                    output_file = args.output
                                    if output_file.endswith('/'):
                                        output_file = os.path.join(output_file, selected_ota.filename)
                                    
                                    # Check if file exists before showing download message
                                    if os.path.exists(output_file):
                                        if selected_ota.checksum and len(selected_ota.checksum) == 64:
                                            if verify_file_hash(output_file, selected_ota.checksum):
                                                print_success(f"File already exists and hash verified: {os.path.basename(output_file)}")
                                                return
                                        else:
                                            print_security_warning(f"File exists but no valid hash provided for verification: {os.path.basename(output_file)}")
                                            return
                                    
                                    print_info(f"Downloading factory image to {output_file}")
                                    if selected_ota.checksum:
                                        print_info(f"Using checksum: {selected_ota.checksum}")
                                    if download_with_progress(selected_ota.download_url, output_file, not args.no_verify_hash, selected_ota.checksum):
                                        print_success("Download completed successfully")
                                    else:
                                        print_error("Download failed")
                                
                                # Output JSON if requested
                                if args.json:
                                    output = {
                                        "device": device,
                                        "friendly_name": scraper.device_names.get(device, device),
                                        "android_version": selected_ota.android_version,
                                        "build_version": selected_ota.build_version,
                                        "download_url": selected_ota.download_url,
                                        "filename": selected_ota.filename,
                                        "checksum": selected_ota.checksum,
                                        "security_patch_level": selected_ota.security_patch_level,
                                        "carrier": selected_ota.carrier,
                                        "region": selected_ota.region,
                                        "is_factory": True
                                    }
                                    print(json.dumps(output, indent=2))
                                return
                            else:
                                print_info("No build selected, exiting...")
                                return
                        except KeyboardInterrupt:
                            print_info("\nOperation cancelled by user")
                            return
                    else:
                        print_error(f"No builds found for device: {device}")
                        return
                else:
                    print_error("Failed to fetch available builds")
                    return
            
            # If we have a specific build or no interactive mode, use get_latest_factory_image
            image = scraper.get_latest_factory_image(
                device,
                include_beta=include_beta,
                prefer_stable=prefer_stable,
                include_carrier=include_carrier,
                include_region_specific=include_region_specific,
                carrier=args.carrier,
                region=args.region,
                specific_build=args.build
            )
        else:
            # If build argument is empty and we're in an interactive session, show available builds
            if args.build == "" and is_interactive_terminal():
                print_info("Fetching available OTA images...")
                html = scraper.fetch_page()
                if html:
                    data = scraper.parse_page(html)
                    if device in data and data[device]:
                        # Apply the same filters as the main OTA selection
                        filtered_otas = data[device]
                        
                        # Filter out beta builds if not included
                        if not args.include_beta:
                            filtered_otas = [ota for ota in filtered_otas if not ota.is_beta]
                            print_info(f"Filtered out beta builds. Remaining: {len(filtered_otas)}")
                        
                        # Filter out carrier-specific builds if not included
                        if not args.include_carrier:
                            filtered_otas = [ota for ota in filtered_otas if not ota.is_carrier]
                            print_info(f"Filtered out carrier builds. Remaining: {len(filtered_otas)}")
                        
                        # Filter out region-specific builds if not included
                        if not args.include_region:
                            filtered_otas = [ota for ota in filtered_otas if not ota.is_region_specific]
                            print_info(f"Filtered out region-specific builds. Remaining: {len(filtered_otas)}")
                        
                        # Filter by specific carrier if requested
                        if args.carrier:
                            filtered_otas = [ota for ota in filtered_otas if ota.carrier == args.carrier]
                            print_info(f"Filtered for carrier {args.carrier}. Remaining: {len(filtered_otas)}")
                        
                        # Filter by specific region if requested
                        if args.region:
                            filtered_otas = [ota for ota in filtered_otas if ota.region == args.region]
                            print_info(f"Filtered for region {args.region}. Remaining: {len(filtered_otas)}")
                        
                        if not filtered_otas:
                            print_error(f"No matching builds found for device {device} after filtering")
                            return
                        
                        print_section_header(f"Available builds for {scraper.device_names.get(device, device)}")
                        
                        # Show active filters
                        print_info("Active filters:")
                        filter_lines = []
                        if not args.include_beta:
                            filter_lines.append("  • Beta builds excluded")
                        if not args.include_carrier:
                            filter_lines.append("  • Carrier-specific builds excluded")
                        if not args.include_region:
                            filter_lines.append("  • Region-specific builds excluded")
                        if args.carrier:
                            filter_lines.append(f"  • Only showing builds for carrier: {args.carrier}")
                        if args.region:
                            filter_lines.append(f"  • Only showing builds for region: {args.region}")
                        if not filter_lines:
                            filter_lines.append("  • No filters applied (showing all builds)")
                        print("\n".join(filter_lines))
                        print()
                        
                        print_info("Available builds (sorted by date):")
                        for idx, ota in enumerate(filtered_otas, 1):
                            build_info = f"{idx}. Android {ota.android_version} ({ota.build_version})"
                            if ota.release_date != "Unknown":
                                build_info += f" - {ota.release_date}"
                            if ota.is_beta:
                                build_info += " [Beta]"
                            if ota.is_carrier:
                                build_info += f" [{ota.carrier}]"
                            if ota.is_region_specific:
                                build_info += f" [{ota.region}]"
                            print(build_info)
                        
                        try:
                            choice = input("\nEnter the number of the build to download (or press Enter to cancel): ").strip()
                            if choice.isdigit() and 1 <= int(choice) <= len(filtered_otas):
                                selected_ota = filtered_otas[int(choice)-1]
                                print_device_info(device, selected_ota, scraper)
                                
                                # Download if output file specified
                                if args.output:
                                    output_file = args.output
                                    if output_file.endswith('/'):
                                        output_file = os.path.join(output_file, selected_ota.filename)
                                    
                                    # Check if file exists before showing download message
                                    if os.path.exists(output_file):
                                        if selected_ota.checksum and len(selected_ota.checksum) == 64:
                                            if verify_file_hash(output_file, selected_ota.checksum):
                                                print_success(f"File already exists and hash verified: {os.path.basename(output_file)}")
                                                return
                                        else:
                                            print_security_warning(f"File exists but no valid hash provided for verification: {os.path.basename(output_file)}")
                                            return
                                    
                                    print_info(f"Downloading OTA to {output_file}")
                                    if selected_ota.checksum:
                                        print_info(f"Using checksum: {selected_ota.checksum}")
                                    if download_with_progress(selected_ota.download_url, output_file, not args.no_verify_hash, selected_ota.checksum):
                                        print_success("Download completed successfully")
                                    else:
                                        print_error("Download failed")
                                
                                # Output JSON if requested
                                if args.json:
                                    output = {
                                        "device": device,
                                        "friendly_name": scraper.device_names.get(device, device),
                                        "android_version": selected_ota.android_version,
                                        "build_version": selected_ota.build_version,
                                        "download_url": selected_ota.download_url,
                                        "filename": selected_ota.filename,
                                        "checksum": selected_ota.checksum,
                                        "security_patch_level": selected_ota.security_patch_level,
                                        "carrier": selected_ota.carrier,
                                        "region": selected_ota.region,
                                        "is_factory": False
                                    }
                                    print(json.dumps(output, indent=2))
                                return
                            else:
                                print_info("No build selected, exiting...")
                                return
                        except KeyboardInterrupt:
                            print_info("\nOperation cancelled by user")
                            return
                    else:
                        print_error(f"No builds found for device: {device}")
                        return
                else:
                    print_error("Failed to fetch available builds")
                    return
            
            # If we have a specific build or no interactive mode, use get_latest_ota
            image = scraper.get_latest_ota(
                device,
                include_beta=include_beta,
                prefer_stable=prefer_stable,
                include_carrier=include_carrier,
                include_region_specific=include_region_specific,
                carrier=args.carrier,
                region=args.region,
                specific_build=args.build
            )
        
        if image:
            print_device_info(device, image, scraper)
            
            # Download if output file specified
            if args.output:
                output_file = args.output
                if output_file.endswith('/'):
                    output_file = os.path.join(output_file, image.filename)
                
                # Check if file exists before showing download message
                if os.path.exists(output_file):
                    if image.checksum and len(image.checksum) == 64:
                        if verify_file_hash(output_file, image.checksum):
                            print_success(f"File already exists and hash verified: {os.path.basename(output_file)}")
                            return
                    else:
                        print_security_warning(f"File exists but no valid hash provided for verification: {os.path.basename(output_file)}")
                        return
                
                print_info(f"Downloading {'factory image' if args.factory else 'OTA'} to {output_file}")
                if image.checksum:
                    print_info(f"Using checksum: {image.checksum}")
                if download_with_progress(image.download_url, output_file, not args.no_verify_hash, image.checksum):
                    print_success("Download completed successfully")
                else:
                    print_error("Download failed")
            
            # Output JSON if requested
            if args.json:
                output = {
                    "device": device,
                    "friendly_name": scraper.device_names.get(device, device),
                    "android_version": image.android_version,
                    "build_version": image.build_version,
                    "download_url": image.download_url,
                    "filename": image.filename,
                    "checksum": image.checksum,
                    "security_patch_level": image.security_patch_level,
                    "carrier": image.carrier,
                    "region": image.region,
                    "is_factory": args.factory
                }
                print(json.dumps(output, indent=2))
        else:
            print_error(f"No {'factory image' if args.factory else 'OTA'} found for device: {device}")
    
    # If no specific action requested, show help
    if not args.check_all and not args.device and not args.family and not args.save_html and not args.list_devices and not args.list_families:
        parser.print_help()


if __name__ == "__main__":
    main()
