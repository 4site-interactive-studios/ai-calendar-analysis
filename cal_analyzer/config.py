"""Configuration loader."""

from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "company_domains": ["4sitestudios.com", "stratovation.digital", "brennaholmes.com"],
    "company_name": "4Site Interactive Studios",
    "organization_names": {},
    "calendar_id": "primary",
    "credentials_file": "credentials.json",
    "token_file": "token.json",
}


def load_config(config_path: str = "config.yaml") -> dict:
    """Load config from YAML file, falling back to defaults."""
    config = dict(DEFAULT_CONFIG)

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            user_config = yaml.safe_load(f) or {}
        config.update(user_config)

    return config
