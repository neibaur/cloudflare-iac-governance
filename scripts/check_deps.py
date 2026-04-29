from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> int:
    terraform_path = shutil.which("terraform")
    if terraform_path is None:
        print(
            "Terraform was not found in this shell. Confirm it is installed and available on PATH.",
            file=sys.stderr,
        )
        return 1

    try:
        completed = subprocess.run(
            [terraform_path, "version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Terraform was found at {terraform_path}, but could not run: {exc}", file=sys.stderr)
        return 1

    print(f"Terraform binary: {terraform_path}")
    print(completed.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
