"""Transactional installation helpers. No network or installation on import."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import time
from typing import Any, Generator, Optional, Union
import urllib.request
import uuid
import zipfile

from configs import ROOT_DIR, safe_urlopen


def digest(path: Union[str, Path]) -> str:
    """Compute the SHA-256 digest of a file.

    Args:
        path (str or Path): Path to the file to hash.

    Returns:
        str: Hexadecimal SHA-256 digest string.
    """
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Union[str, Path], data: Union[dict[str, Any], list[Any]]) -> None:
    """Atomically write data as formatted JSON to a file.

    Args:
        path (str or Path): Target file path where JSON data will be saved.
        data (dict or list): Data structure to serialize to JSON.
    """
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path_obj.parent, prefix=path_obj.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path_obj)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def read_json(path: Union[str, Path]) -> dict[str, Any]:
    """Safely read and parse a JSON file.

    Args:
        path (str or Path): Path to the JSON file.

    Returns:
        dict: Parsed JSON data as a dictionary, or an empty dictionary if reading fails.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, ValueError):
        return {}


@contextmanager
def file_lock(path: Union[str, Path]) -> Generator[None, None, None]:
    """Acquire a cross-platform non-blocking file lock.

    OS lock is released on crashes; does not unlink an active lock inode.

    Args:
        path (str or Path): File path used as the lock marker.

    Raises:
        RuntimeError: If another process already holds the lock.
    """
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(path_obj, "a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f"Another instance owns {path_obj}") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_UN)


def download(url: str, destination: Union[str, Path], expected_sha256: Optional[str] = None) -> None:
    """Download a file from a URL to a target destination with optional SHA-256 verification.

    Publishes a complete verified transfer atomically; never leaves a partial target.

    Args:
        url (str): Remote URL to download from.
        destination (str or Path): Path where the final file should be saved.
        expected_sha256 (str, optional): Expected SHA-256 hash. Defaults to None.

    Raises:
        RuntimeError: If the download fails, is incomplete, or hash verification fails.
    """
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=dest_path.parent, prefix="download-")
    try:
        with os.fdopen(fd, "wb") as output:
            request = urllib.request.Request(url, headers={"User-Agent": "FrugalTraining-Setup/2"})
            with safe_urlopen(request, timeout=60) as response:
                expected_length = response.headers.get("Content-Length")
                shutil.copyfileobj(response, output)
                length = output.tell()
        if not length or (expected_length is not None and length != int(expected_length)):
            raise RuntimeError(f"Incomplete download: {url}")
        if expected_sha256 and digest(temp_name).lower() != expected_sha256.lower():
            raise RuntimeError(f"SHA256 mismatch: {url}")
        os.replace(temp_name, dest_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def safe_extract(archive: Union[str, Path], destination: Union[str, Path]) -> None:
    """Safely extract a ZIP or tarball archive into a target directory.

    Protects against path traversal (Zip Slip / Tar Slip) vulnerabilities and rejects unsafe entries.

    Args:
        archive (str or Path): Path to the ZIP or tar archive file.
        destination (str or Path): Destination directory to extract into.

    Raises:
        ValueError: If an archive entry contains unsafe paths or unsupported link structures.
    """
    dest_dir = Path(destination).resolve()

    def validate(name: str) -> None:
        """Validate that an archive entry name does not traverse outside the target directory."""
        if "\\" in name or ":" in name or not (dest_dir / name).resolve().is_relative_to(dest_dir):
            raise ValueError(f"Unsafe archive member: {name}")

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as stream:
            for member in stream.infolist():
                validate(member.filename)
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Archive symlinks are not supported")
            stream.extractall(dest_dir)
    else:
        with tarfile.open(archive) as stream:
            for member in stream.getmembers():
                validate(member.name)
                if not (member.isfile() or member.isdir()):
                    raise ValueError("Archive links and devices are not supported")
            for member in stream.getmembers():
                target = dest_dir / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with stream.extractfile(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(member.mode & 0o777)


def publish_directory(staged: Union[str, Path], target: Union[str, Path]) -> None:
    """Atomically publish a staged directory to a target directory location.

    Keeps previous installations recoverable (including local edits) by backing them up before replacing.

    Args:
        staged (str or Path): Path to the staged directory ready for publishing.
        target (str or Path): Target installation directory path.

    Raises:
        RuntimeError: If cleanup or path verification fails during error handling.
    """
    staged_path = Path(staged)
    target_path = Path(target)
    backup: Optional[Path] = None
    prepared: Optional[Path] = None
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        backup = target_path.with_name(target_path.name + ".previous-" + uuid.uuid4().hex[:8])
        target_path.rename(backup)
    try:
        for attempt in range(5):
            try:
                staged_path.rename(target_path)
                break
            except PermissionError:
                if attempt == 4:
                    prepared = target_path.with_name(target_path.name + ".installing-" + uuid.uuid4().hex[:8])
                    shutil.copytree(staged_path, prepared)
                    prepared.rename(target_path)
                    break
                time.sleep(0.25 * (2 ** attempt))
    except Exception:
        if backup is not None:
            backup.rename(target_path)
        raise
    finally:
        if prepared and prepared.exists():
            if (
                prepared.resolve().parent != target_path.resolve().parent
                or not prepared.name.startswith(target_path.name + ".installing-")
            ):
                raise RuntimeError("Unexpected staging path; refusing cleanup")
            shutil.rmtree(prepared)
    if backup:
        print(f"[+] Previous installation preserved at {backup}")


def portable_path(path: Union[str, Path]) -> str:
    """Convert an absolute path to a relative path from ROOT_DIR if applicable.

    Args:
        path (str or Path): The path to make relative or portable.

    Returns:
        str: Relative path string if within ROOT_DIR, otherwise absolute path string.
    """
    resolved_path = Path(path).resolve()
    return str(resolved_path.relative_to(ROOT_DIR)) if resolved_path.is_relative_to(ROOT_DIR) else str(resolved_path)
