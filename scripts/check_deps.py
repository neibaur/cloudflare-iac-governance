from __future__ import annotations

import shutil
import subprocess
import sys
from importlib import metadata, util


def check_python_dependency(display_name: str, modules: tuple[str, ...]) -> bool:
    for module in modules:
        if util.find_spec(module) is not None:
            version = dependency_version(display_name)
            suffix = f" ({version})" if version else ""
            print(f"{display_name}: available via module '{module}'{suffix}")
            return True

    print(
        f"{display_name} was not found in this Python interpreter: {sys.executable}",
        file=sys.stderr,
    )
    return False


def dependency_version(display_name: str) -> str | None:
    candidates = {
        "pytest": ("pytest",),
        "python-cloudflare": ("cloudflare", "python-cloudflare"),
    }

    for package_name in candidates.get(display_name, (display_name,)):
        try:
            return metadata.version(package_name)
        except metadata.PackageNotFoundError:
            continue

    return None


def main() -> int:
    exit_code = 0

    print(f"Python interpreter: {sys.executable}")

    terraform_path = shutil.which("terraform")
    if terraform_path is None:
        local_terraform_path = r"C:\terraform\terraform.exe"
        if shutil.which(local_terraform_path) is not None:
            terraform_path = local_terraform_path

    if terraform_path is None:
        print(
            "Terraform was not found in this shell. Confirm it is installed at "
            r"C:\terraform\terraform.exe or available on PATH.",
            file=sys.stderr,
        )
        exit_code = 1
    else:
        try:
            completed = subprocess.run(
                [terraform_path, "version"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"Terraform was found at {terraform_path}, but could not run: {exc}", file=sys.stderr)
            exit_code = 1
        else:
            print(f"Terraform binary: {terraform_path}")
            print(completed.stdout.strip())

    if not check_python_dependency("pytest", ("pytest",)):
        exit_code = 1

    if not check_python_dependency("python-cloudflare", ("CloudFlare", "cloudflare")):
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
