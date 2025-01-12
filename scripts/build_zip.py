from __future__ import annotations

from pathlib import Path
from shutil import copy2
from shutil import copytree
from shutil import make_archive
from shutil import rmtree
from subprocess import run


def build_lambda_zip() -> None:
    project_dir = Path(__file__).parent.parent
    build_dir = project_dir / "build"
    zip_file = project_dir / "dist" / "lambda.zip"
    requirements_file = project_dir / "requirements.txt"

    # Clean up old builds
    if build_dir.exists():
        rmtree(build_dir)
    if zip_file.exists():
        zip_file.unlink()

    # Create build directory
    build_dir.mkdir()

    # Install dependencies into the build directory
    run(
        ["pip", "install", "-r",
            str(requirements_file), "--target", str(build_dir)],
        check=True,
    )

    # Copy application code
    app_dir = project_dir / "src" / "lambda"
    for item in app_dir.iterdir():
        if item.is_dir():
            copytree(item, build_dir / item.name)
        else:
            copy2(item, build_dir / item.name)

    # Create the ZIP file
    make_archive(str(zip_file.with_suffix("")), "zip", root_dir=build_dir)

    print(f"Lambda package created: {zip_file}")


if __name__ == "__main__":
    build_lambda_zip()
