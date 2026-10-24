"""LOCAL-16: explicit model profiles; no inference or model mutation on import."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Profile:
    name: str
    base_model: str
    purpose: str

PROFILES = {
    "principal": Profile("principal", "nemotron-3-nano:4b", "controlled Python editing and debugging"),
    "alternativo": Profile("alternativo", "qwen3.5:4b", "controlled Python editing and review"),
    "economico": Profile("economico", "qwen3.5:2b", "small, bounded Python edits"),
}

def select_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError("UNKNOWN_PROFILE") from exc
