"""Build the submission ZIP: src/, the required artifacts, and AI_USAGE.md.

Never includes .env, and refuses to package if the API key from .env or the
environment appears in any file being zipped.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

from dotenv import dotenv_values

REQUIRED_ARTIFACTS = [
    "fix.patch",
    "part1-trajectory.json",
    "django__django-15368.patch",
    "django__django-15368-trajectory.json",
    "token-usage-analysis.md",
    "part3-trajectory.json",
    "game-result.json",
    "part3-no-legal-moves-deepseek.json",
    "part3-no-legal-moves-deepseek-result.json",
    "part3-legal-moves-deepseek.json",
    "part3-legal-moves-deepseek-result.json",
    "part3-no-legal-moves-gpt-oss.json",
    "part3-no-legal-moves-gpt-oss-result.json",
    "part3-legal-moves-gpt-oss.json",
    "part3-legal-moves-gpt-oss-result.json",
    "observation-experiment.md",
    "part3-python-skill-trajectory.json",
]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "src/assignment/agent").glob("*.py"))
    missing = []
    for name in REQUIRED_ARTIFACTS:
        path = root / "artifacts" / name
        if path.is_file():
            files.append(path)
        else:
            missing.append(name)
    usage = root / "AI_USAGE.md"
    if usage.is_file():
        files.append(usage)
    else:
        missing.append("AI_USAGE.md")

    secrets = {
        value
        for value in [os.environ.get("OPENAI_API_KEY"), dotenv_values(root / ".env").get("OPENAI_API_KEY")]
        if value and len(value) >= 12 and not value.startswith("replace-")
    }
    for path in files:
        text = path.read_text(errors="ignore")
        if any(secret in text for secret in secrets):
            raise SystemExit(f"Refusing to package: your API key appears in {path.relative_to(root)}")

    out = root / "submission.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root))
    print(f"Wrote {out.relative_to(root)} with {len(files)} files.")
    if missing:
        print("Missing (not included):\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    main()
