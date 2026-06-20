import sys
from pathlib import Path

# Make the project root importable so `agents.intake_agent` resolves
# regardless of how `adk web` invokes this module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agents.intake_agent import intake_agent as root_agent  # noqa: E402,F401
