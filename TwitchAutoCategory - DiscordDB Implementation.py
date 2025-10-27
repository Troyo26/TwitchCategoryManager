import obspython as obs  # type: ignore
import json
import os
import threading
import time
import requests
import psutil  # type: ignore
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import socket

# Constants
GAMES_JSON_FILE = "games.json"
DISCORD_CACHE_FILE = "discord_detectable_cache.json"
DISCORD_URL = "https://discord.com/api/v9/applications/detectable"
DISCORD_CACHE_TTL = 24 * 3600  # refresh every 24 hours


class TwitchAutoCategory:
    def __init__(self):
        # Twitch authentication
        self.client_id = None
        self.client_secret = None
        self.access_token = None
        self.refresh_token = None
        self.redirect_uri = None
        self.token_lock = threading.Lock()
        
        # Process monitoring
        self.monitor_thread = None
        self.stop_monitoring = False
        self.current_category = "Just Chatting"
        
        # Game mappings
        self.process_priorities = {}    # exe -> priority (int)
        self.process_categories = {}    # exe -> category (str)
        self.discord_exe_map = {}       # exe -> discord app name (str)
        self.cache_lock = threading.Lock()
        
        # Settings reference
        self.current_settings = None
        
        # Load data
        self.load_games_json()
        threading.Thread(target=self.ensure_discord_cache, daemon=True).start()

    # ========== OBS Script Hooks ==========
    
    def script_description(self):
        return ("Automatically updates Twitch category based on running applications.\n"
                "Uses custom game mappings (priority) + Discord detectable apps database (fallback).")
    
    def script_properties(self):
        props = obs.obs_properties_create()
        
        # Configuration section
        obs.obs_properties_add_text(props, "client_id", "Twitch Client ID", obs.OBS_TEXT_DEFAULT)
        obs.obs_properties_add_text(props, "client_secret", "Twitch Client Secret", obs.OBS_TEXT_PASSWORD)
        obs.obs_properties_add_text(props, "broadcaster_name", "Broadcaster Username", obs.OBS_TEXT_DEFAULT)
        obs.obs_properties_add_button(props, "save_config_button", "Save Configuration", save_config_button_clicked)
        
        # Twitch authentication
        obs.obs_properties_add_button(props, "login_button", "Login with Twitch", login_button_clicked)
        
        # Discord database
        obs.obs_properties_add_button(props, "refresh_discord", "Refresh Discord DB", refresh_discord_button_clicked)
        
        # Add custom game mapping
        obs.obs_properties_add_text(props, "exe_name", "EXE Name (e.g., game.exe)", obs.OBS_TEXT_DEFAULT)
        obs.obs_properties_add_text(props, "category_name", "Twitch Category", obs.OBS_TEXT_DEFAULT)
        obs.obs_properties_add_int(props, "priority", "Priority (higher = more important)", 0, 100, 1)
        obs.obs_properties_add_button(props, "add_game_button", "Add Game", add_game_button_clicked)
        
        # Utility
        obs.obs_properties_add_button(props, "list_sample", "Print Sample Mappings", print_sample_button_clicked)
        
        return props
    
    def script_update(self, settings):
        self.current_settings = settings
    
    def script_load(self, settings):
        # Load Twitch credentials
        self.client_id, self.client_secret = self.load_config()
        self.load_access_tokens()
        
        # Start monitoring if authenticated
        if self.access_token and self.refresh_token:
            if self.validate_token() or self.refresh_access_token():
                self.start_process_monitor()
            else:
                self.log("Failed to validate or refresh tokens. Please re-authenticate using 'Login with Twitch'.")
        else:
            self.log("No valid tokens found. Please authenticate using 'Login with Twitch'.")
    
    def script_unload(self):
        self.stop_monitoring = True
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)

    # ========== Config & Token Management ==========
    
    def load_config(self):
        """Load Twitch client_id and client_secret from config.json"""
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('client_id'), config.get('client_secret')
            except Exception as e:
                self.log(f"Error reading config.json: {e}")
        else:
            self.log("Config file not found. Please use 'Save Configuration' button to create it.")
        return None, None
    
    def save_config_button_clicked(self):
        """Save configuration from text boxes to config.json"""
        if not self.current_settings:
            self.log("Settings unavailable. Click Apply in OBS first.", obs.LOG_WARNING)
            return
        
        client_id = obs.obs_data_get_string(self.current_settings, "client_id").strip()
        client_secret = obs.obs_data_get_string(self.current_settings, "client_secret").strip()
        broadcaster_name = obs.obs_data_get_string(self.current_settings, "broadcaster_name").strip()
        
        if not client_id or not client_secret or not broadcaster_name:
            self.log("All fields (Client ID, Client Secret, Broadcaster Username) are required.", obs.LOG_WARNING)
            return
        
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            config_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "broadcaster_name": broadcaster_name
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            
            # Update instance variables
            self.client_id = client_id
            self.client_secret = client_secret
            
            self.log("✓ Configuration saved successfully to config.json!")
            self.log("You can now click 'Login with Twitch' to authenticate.")
        except Exception as e:
            self.log(f"Failed to save config.json: {e}", obs.LOG_WARNING)
    
    def load_access_tokens(self):
        """Load access_token and refresh_token from tokens.json"""
        token_path = os.path.join(os.path.dirname(__file__), 'tokens.json')
        if os.path.exists(token_path):
            try:
                with open(token_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    with self.token_lock:
                        self.access_token = data.get("access_token")
                        self.refresh_token = data.get("refresh_token")
            except Exception as e:
                self.log(f"Error reading tokens.json: {e}")
    
    def save_access_tokens(self):
        """Save access_token and refresh_token to tokens.json"""
        token_path = os.path.join(os.path.dirname(__file__), 'tokens.json')
        try:
            with self.token_lock:
                data = {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token
                }
            with open(token_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.log(f"Error saving tokens: {e}")

    # ========== Twitch OAuth Authentication ==========
    
    def login_button_clicked(self):
        """Initiate Twitch OAuth flow"""
        threading.Thread(target=self.start_auth, daemon=True).start()
    
    def start_auth(self):
        """Start OAuth server and open browser for authentication"""
        if not self.client_id or not self.client_secret:
            self.log("Client ID or secret not configured. Please check config.json.", obs.LOG_WARNING)
            return
        
        self.redirect_uri = "http://localhost:17563"
        port = 17563
        
        class OAuthHandler(BaseHTTPRequestHandler):
            def log_message(inner_self, format, *args):
                pass  # Suppress server logs
            
            def do_GET(inner_self):
                if "code=" in inner_self.path:
                    code = inner_self.path.split("code=")[1].split("&")[0]
                    self.get_access_token(code)
                    inner_self.send_response(200)
                    inner_self.end_headers()
                    inner_self.wfile.write(b"Authentication successful! You can close this window.")
                    threading.Thread(target=inner_self.server.shutdown).start()
        
        server = HTTPServer(('localhost', port), OAuthHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        
        auth_url = (f"https://id.twitch.tv/oauth2/authorize?"
                   f"client_id={self.client_id}&"
                   f"redirect_uri={self.redirect_uri}&"
                   f"response_type=code&"
                   f"scope=channel:manage:broadcast")
        webbrowser.open(auth_url)
        self.log(f"OAuth server started on port {port}. Opening browser...")
    
    def find_free_port(self):
        """Find an available port for OAuth callback"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    
    def get_access_token(self, code):
        """Exchange OAuth code for access token"""
        token_url = "https://id.twitch.tv/oauth2/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }
        try:
            response = requests.post(token_url, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            
            with self.token_lock:
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data["refresh_token"]
            
            self.save_access_tokens()
            self.log("Successfully logged in to Twitch!")
            
            # Start monitoring if not already running
            if not self.monitor_thread or not self.monitor_thread.is_alive():
                self.start_process_monitor()
        except requests.exceptions.RequestException as e:
            self.log(f"Failed to obtain access token: {e}", obs.LOG_WARNING)
    
    def refresh_access_token(self):
        """Refresh the Twitch access token using refresh token"""
        with self.token_lock:
            if not self.refresh_token:
                self.log("No refresh token available. Please re-authenticate.", obs.LOG_WARNING)
                return False
            
            token_url = "https://id.twitch.tv/oauth2/token"
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
        
        try:
            response = requests.post(token_url, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            
            with self.token_lock:
                self.access_token = token_data["access_token"]
                if "refresh_token" in token_data:
                    self.refresh_token = token_data["refresh_token"]
            
            self.save_access_tokens()
            self.log("Successfully refreshed access token!")
            return True
        except requests.exceptions.RequestException as e:
            self.log(f"Failed to refresh access token: {e}", obs.LOG_WARNING)
            return False
    
    def validate_token(self):
        """Validate current access token"""
        with self.token_lock:
            if not self.access_token:
                return False
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
        
        try:
            response = requests.get('https://id.twitch.tv/oauth2/validate', 
                                   headers=headers, timeout=10)
            return response.status_code == 200
        except Exception as e:
            self.log(f"Error during token validation: {e}")
            return False

    # ========== Custom Games JSON ==========
    
    def load_games_json(self):
        """Load custom game mappings from games.json"""
        self.process_priorities.clear()
        self.process_categories.clear()
        
        path = os.path.join(os.path.dirname(__file__), GAMES_JSON_FILE)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for g in data.get("games", []):
                        exe = g.get("exe", "").casefold()
                        if not exe:
                            continue
                        self.process_priorities[exe] = int(g.get("priority", 0))
                        self.process_categories[exe] = g.get("category", "")
                self.log(f"Loaded {len(self.process_categories)} custom game mappings.")
            except Exception as e:
                self.log(f"Error reading {GAMES_JSON_FILE}: {e}")
        else:
            # Create empty template
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({"games": []}, f, indent=2)
            self.log("Created new games.json template.")
    
    def add_game_button_clicked(self):
        """Add a new game mapping to games.json"""
        if not self.current_settings:
            self.log("Settings unavailable. Click Apply in OBS first.", obs.LOG_WARNING)
            return
        
        exe_name = obs.obs_data_get_string(self.current_settings, "exe_name").strip()
        category_name = obs.obs_data_get_string(self.current_settings, "category_name").strip()
        priority = obs.obs_data_get_int(self.current_settings, "priority")
        
        if not exe_name or not category_name:
            self.log("EXE name and category cannot be empty.", obs.LOG_WARNING)
            return
        
        exe_key = exe_name.casefold()
        self.process_categories[exe_key] = category_name
        self.process_priorities[exe_key] = int(priority)
        
        path = os.path.join(os.path.dirname(__file__), GAMES_JSON_FILE)
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {"games": []}
            
            # Remove duplicates
            data["games"] = [g for g in data.get("games", []) 
                           if g.get("exe", "").casefold() != exe_key]
            
            # Add new entry
            data["games"].append({
                "exe": exe_name,
                "category": category_name,
                "priority": int(priority)
            })
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            self.log(f"Added: {exe_name} -> {category_name} (priority {priority})")
        except Exception as e:
            self.log(f"Failed to update {GAMES_JSON_FILE}: {e}", obs.LOG_WARNING)

    # ========== Discord Database ==========
    
    def ensure_discord_cache(self):
        """Ensure Discord database cache exists and is fresh"""
        try:
            with self.cache_lock:
                cache_path = os.path.join(os.path.dirname(__file__), DISCORD_CACHE_FILE)
                need_fetch = True
                
                if os.path.exists(cache_path):
                    try:
                        with open(cache_path, 'r', encoding='utf-8') as f:
                            cache = json.load(f)
                        ts = cache.get("_fetched_at", 0)
                        
                        if time.time() - ts < DISCORD_CACHE_TTL:
                            # Load from cache
                            self.discord_exe_map = cache.get("exe_map", {})
                            need_fetch = False
                            self.log(f"Loaded Discord DB cache ({len(self.discord_exe_map)} executables).")
                    except Exception:
                        need_fetch = True
                
                if need_fetch:
                    self.log("Fetching Discord detectable apps (may take a few seconds)...")
                    self.fetch_and_cache_discord_db(cache_path)
        except Exception as e:
            self.log(f"Error in ensure_discord_cache: {e}")
    
    def fetch_and_cache_discord_db(self, cache_path):
        """Fetch Discord detectable apps and cache locally"""
        try:
            resp = requests.get(DISCORD_URL, timeout=30)
            resp.raise_for_status()
            apps = resp.json()
            exe_map = {}
            
            for app in apps:
                game_name = app.get("name")
                if not game_name:
                    continue
                
                # Map executables
                executables = app.get("executables", [])
                for exe_entry in executables:
                    exe_name = exe_entry.get("name")
                    os_type = exe_entry.get("os")
                    if exe_name and os_type == "win32":
                        exe_map[exe_name.casefold()] = game_name
                
                # Map aliases
                for alias in app.get("aliases", []):
                    exe_map[alias.casefold()] = game_name
            
            # Save to cache
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "_fetched_at": int(time.time()),
                    "exe_map": exe_map
                }, f, indent=2)
            
            with self.cache_lock:
                self.discord_exe_map = exe_map
            
            self.log(f"Fetched and cached Discord DB ({len(exe_map)} executables).")
        except Exception as e:
            self.log(f"Failed to fetch Discord DB: {e}", obs.LOG_WARNING)
    
    def manual_refresh_discord(self):
        """Manually refresh Discord database"""
        cache_path = os.path.join(os.path.dirname(__file__), DISCORD_CACHE_FILE)
        threading.Thread(target=self.fetch_and_cache_discord_db, 
                        args=(cache_path,), daemon=True).start()

    # ========== Twitch Category Update ==========
    
    def update_twitch_category(self, category):
        """Update Twitch stream category"""
        if category == self.current_category:
            return
        
        with self.token_lock:
            if not self.access_token:
                self.log("Not authenticated with Twitch. Please login first.", obs.LOG_WARNING)
                return
            headers = {
                'Client-ID': self.client_id,
                'Authorization': f'Bearer {self.access_token}'
            }
        
        # Get broadcaster info
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                broadcaster_name = config.get('broadcaster_name')
                if not broadcaster_name:
                    self.log("broadcaster_name not found in config.json", obs.LOG_WARNING)
                    return
        except Exception as e:
            self.log(f"Error reading config.json: {e}", obs.LOG_WARNING)
            return
        
        try:
            # Get broadcaster ID
            user_response = requests.get(
                f'https://api.twitch.tv/helix/users?login={broadcaster_name}',
                headers=headers, timeout=10
            )
            user_response.raise_for_status()
            user_data = user_response.json()['data']
            if not user_data:
                self.log(f"Broadcaster not found: {broadcaster_name}", obs.LOG_WARNING)
                return
            broadcaster_id = user_data[0]['id']
            
            # Search for category
            category_response = requests.get(
                f'https://api.twitch.tv/helix/search/categories?query={category}',
                headers=headers, timeout=10
            )
            category_response.raise_for_status()
            categories = category_response.json()['data']
            
            if not categories:
                self.log(f"Category not found: {category}", obs.LOG_WARNING)
                return
            
            # Find exact match or use first result
            exact_match = next(
                (cat for cat in categories if cat['name'].casefold() == category.casefold()),
                None
            )
            game_id = exact_match['id'] if exact_match else categories[0]['id']
            
            if not exact_match:
                self.log(f"Using closest match: {categories[0]['name']}")
            
            # Update channel
            update_response = requests.patch(
                f'https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}',
                headers=headers,
                json={'game_id': game_id},
                timeout=10
            )
            update_response.raise_for_status()
            
            self.current_category = category
            self.log(f"✓ Updated Twitch category to: {category}")
        except requests.exceptions.RequestException as e:
            self.log(f"Failed to update category: {e}", obs.LOG_WARNING)
            
            # Try to refresh token if unauthorized
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 401:
                self.log("Token may be expired. Attempting to refresh...")
                if self.refresh_access_token():
                    # Retry once after refresh
                    self.update_twitch_category(category)

    # ========== Process Detection ==========
    
    def check_processes(self):
        """
        Check running processes and return selected category.
        Priority order:
        1. Custom mappings (games.json) - by priority value
        2. Discord database (fallback, priority 0)
        3. "Just Chatting" (default)
        """
        try:
            highest_priority = -1
            selected_category = None
            
            # Prepare lowercase lookup
            pp = {k.casefold(): v for k, v in self.process_priorities.items()}
            pc = {k.casefold(): v for k, v in self.process_categories.items()}
            
            # Get Discord map snapshot (thread-safe)
            with self.cache_lock:
                discord_map = dict(self.discord_exe_map)
            
            for proc in psutil.process_iter(['name']):
                pname = proc.info.get('name') or ""
                if not pname:
                    continue
                name = pname.casefold()
                
                # Check custom mappings first (higher priority)
                if name in pc:
                    prio = pp.get(name, 0)
                    if prio > highest_priority:
                        highest_priority = prio
                        selected_category = pc[name]
                    continue
                
                # Fallback to Discord database (priority 0)
                if name in discord_map:
                    if 0 > highest_priority:
                        highest_priority = 0
                        selected_category = discord_map[name]
            
            return selected_category or "Just Chatting"
        except Exception as e:
            self.log(f"Error checking processes: {e}", obs.LOG_WARNING)
            return "Just Chatting"

    # ========== Process Monitor Thread ==========
    
    def start_process_monitor(self):
        """Start background thread to monitor processes"""
        self.stop_monitoring = False
        
        def monitor():
            while not self.stop_monitoring:
                try:
                    # Validate token periodically
                    if not self.validate_token():
                        if not self.refresh_access_token():
                            self.log("Token invalid and refresh failed. Please re-authenticate.")
                            time.sleep(60)
                            continue
                    
                    # Check processes and update category
                    category = self.check_processes()
                    self.update_twitch_category(category)
                    
                except Exception as e:
                    self.log(f"Monitor error: {e}", obs.LOG_WARNING)
                
                time.sleep(60)  # Check every 60 seconds
        
        self.monitor_thread = threading.Thread(target=monitor, daemon=True)
        self.monitor_thread.start()
        self.log("Process monitor started.")

    # ========== Utilities ==========
    
    def print_sample_mappings(self):
        """Print sample mappings to OBS log"""
        self.log("=== Custom Mappings (first 10) ===")
        for i, (k, v) in enumerate(self.process_categories.items()):
            if i >= 10:
                break
            prio = self.process_priorities.get(k, 0)
            self.log(f"  {k} -> {v} (priority {prio})")
        
        with self.cache_lock:
            self.log("=== Discord Mappings (first 10) ===")
            for i, (k, v) in enumerate(self.discord_exe_map.items()):
                if i >= 10:
                    break
                self.log(f"  {k} -> {v}")
    
    def log(self, message, level=obs.LOG_INFO):
        """Log message to OBS"""
        obs.script_log(level, message)


# ========== Module-Level Callbacks ==========

def login_button_clicked(props, prop):
    """Callback for Login with Twitch button"""
    twitch_bot.login_button_clicked()
    return True


def refresh_discord_button_clicked(props, prop):
    """Callback for Refresh Discord DB button"""
    twitch_bot.manual_refresh_discord()
    return True


def add_game_button_clicked(props, prop):
    """Callback for Add Game button"""
    twitch_bot.add_game_button_clicked()
    return True


def save_config_button_clicked(props, prop):
    """Callback for Save Configuration button"""
    twitch_bot.save_config_button_clicked()
    return True


def print_sample_button_clicked(props, prop):
    """Callback for Print Sample Mappings button"""
    twitch_bot.print_sample_mappings()
    return True


# ========== OBS Interface ==========

twitch_bot = TwitchAutoCategory()

# Expose OBS hooks
script_description = twitch_bot.script_description
script_properties = twitch_bot.script_properties
script_update = twitch_bot.script_update
script_load = twitch_bot.script_load
script_unload = twitch_bot.script_unload
