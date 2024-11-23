import os
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict

@dataclass
class TranslatorConfig:
    # Translator settings
    translator: str = "sugoi"
    target_language: str = "ENG"
    upscale_ratio: float = 1.0
    colorize: bool = True
    use_gpu: bool = False
    force_uppercase: bool = False
    ignore_error: bool = False
    
    # Rawkuma settings
    manga_directory: str = str(Path.home() / "Documents" / "rawkuma")

    @staticmethod
    def get_translators() -> Dict[str, str]:
        return {
            "google": "Google Translate",
            "youdao": "YouDao",
            "baidu": "Baidu",
            "deepl": "DeepL",
            "papago": "Papago",
            "caiyun": "Caiyun",
            "gpt3": "GPT-3",
            "gpt3.5": "GPT-3.5",
            "gpt4": "GPT-4",
            "none": "None",
            "original": "Original",
            "offline": "Offline",
            "nllb": "NLLB",
            "nllb_big": "NLLB Big",
            "sugoi": "Sugoi",
            "jparacrawl": "JParaCrawl",
            "jparacrawl_big": "JParaCrawl Big",
            "m2m100": "M2M100",
            "m2m100_big": "M2M100 Big",
            "sakura": "Sakura"
        }
    
    @staticmethod
    def get_languages() -> Dict[str, str]:
        return {
            "ENG": "English",
            "CHS": "Chinese Simplified",
            "CHT": "Chinese Traditional",
            "CSY": "Czech",
            "NLD": "Dutch",
            "FRA": "French",
            "DEU": "German",
            "HUN": "Hungarian",
            "ITA": "Italian",
            "JPN": "Japanese",
            "KOR": "Korean",
            "PLK": "Polish",
            "PTB": "Portuguese (Brazil)",
            "ROM": "Romanian",
            "RUS": "Russian",
            "ESP": "Spanish",
            "TRK": "Turkish",
            "UKR": "Ukrainian",
            "VIN": "Vietnamese",
            "ARA": "Arabic",
            "CNR": "Montenegrin",
            "SRP": "Serbian",
            "HRV": "Croatian",
            "THA": "Thai",
            "IND": "Indonesian",
            "FIL": "Filipino"
        }

class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "manga-translator"
        self.config_file = self.config_dir / "appconfig.ini"
        self.config = self.load_config()
    
    def load_config(self) -> TranslatorConfig:
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    return TranslatorConfig(**data)
            
            # Create default config if not exists
            config = TranslatorConfig()
            self.save_config(config)
            return config
            
        except Exception as e:
            print(f"Error loading config: {e}")
            return TranslatorConfig()
    
    def save_config(self, config: TranslatorConfig):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(asdict(config), f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}") 