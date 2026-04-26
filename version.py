"""Single source of truth for the Ptarmigan version.

Imported from anywhere that needs the version string (project.json
metadata, About dialog, --version CLI flag, etc.). Bump in this file
only — do not duplicate the literal elsewhere.
"""

__version__ = "0.1.0"
