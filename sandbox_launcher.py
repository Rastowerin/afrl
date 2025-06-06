#!/usr/bin/env python3
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple


def hash_file(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha.update(chunk)
    return sha.hexdigest()


def merkle_hash(directory: Path) -> str:
    entries = []
    for root, dirs, files in os.walk(directory, topdown=True):
        for name in sorted(files):
            file_path = Path(root) / name
            entries.append((str(file_path.relative_to(directory)), hash_file(file_path)))
        for name in sorted(dirs):
            dir_path = Path(root) / name
            entries.append((str(dir_path.relative_to(directory)) + '/', ''))
    sha = hashlib.sha256()
    for name, digest in sorted(entries):
        sha.update(name.encode())
        sha.update(digest.encode())
    return sha.hexdigest()


def compute_initial_hashes(paths: List[Path]) -> dict:
    return {str(p): merkle_hash(p) for p in paths}


def compute_final_hashes(paths: List[Path]) -> dict:
    return compute_initial_hashes(paths)


def diff_hashes(initial: dict, final: dict) -> List[str]:
    changes = []
    for path, start_hash in initial.items():
        end_hash = final.get(path)
        if start_hash != end_hash:
            changes.append(path)
    return changes


def snapshot_directory(directory: Path) -> Dict[str, str]:
    """Return mapping of relative file paths to hashes."""
    mapping: Dict[str, str] = {}
    for root, _, files in os.walk(directory, topdown=True):
        for name in files:
            file_path = Path(root) / name
            rel = str(file_path.relative_to(directory))
            mapping[rel] = hash_file(file_path)
    return mapping


def snapshot_directories(paths: List[Path]) -> Dict[str, Dict[str, str]]:
    return {str(p): snapshot_directory(p) for p in paths}


def diff_snapshots(initial: Dict[str, Dict[str, str]],
                   final: Dict[str, Dict[str, str]]) -> Dict[str, List[str]]:
    """Return list of changed files for each path."""
    result: Dict[str, List[str]] = {}
    for path, start in initial.items():
        end = final.get(path, {})
        changed: List[str] = []
        # Detect modified or removed files
        for file, digest in start.items():
            if file not in end:
                changed.append(f'Removed: {file}')
            elif end[file] != digest:
                changed.append(f'Modified: {file}')
        # Detect new files
        for file in end.keys() - start.keys():
            changed.append(f'Added: {file}')
        if changed:
            result[path] = changed
    return result


def prepare_overlays(paths: List[Path]) -> Dict[Path, Path]:
    mapping: Dict[Path, Path] = {}
    for p in paths:
        tmp = Path(tempfile.mkdtemp(prefix=p.name.replace('/', '_') + '_overlay_'))
        subprocess.check_call(['rsync', '-a', f'{p}/', f'{tmp}/'])
        mapping[p] = tmp
    return mapping


def cleanup_overlays(mapping: Dict[Path, Path]) -> None:
    for overlay in mapping.values():
        subprocess.run(['rm', '-rf', str(overlay)], check=False)


def build_docker_cmd(image: str, overlay_paths: List[Path], command: List[str], user: str) -> List[str]:
    cmd = [
        'docker', 'run', '--rm', '-it',
        '--runtime=runsc',  # gVisor runtime
        '--network', 'none',  # no network access
        '--read-only',
        '--tmpfs', '/tmp',
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges',
        '--pids-limit', '64',
        '--memory', '512m'
    ]
    for p in overlay_paths:
        host = str(p.resolve())
        container = host
        cmd += ['-v', f'{host}:{container}:rw']
    cmd += ['--user', user]
    cmd.append(image)
    cmd += command
    return cmd


def run_container(cmd: List[str]) -> int:
    print('Launching sandbox:', ' '.join(cmd))
    result = subprocess.run(cmd)
    return result.returncode


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description='Launch secure sandbox.')
    parser.add_argument('--image', required=True, help='Docker image to use.')
    parser.add_argument('--edit', action='append', default=[], help='Path to directory allowed for editing.')
    parser.add_argument('--user', default='dev', help='User inside the container to run as.')
    parser.add_argument('command', nargs=argparse.REMAINDER, default=['/bin/bash'],
                        help='Command to run inside the sandbox.')
    args = parser.parse_args(argv)

    edit_paths = [Path(p).resolve() for p in args.edit]
    for p in edit_paths:
        if not p.exists() or not p.is_dir():
            print(f'Editable path {p} does not exist or is not a directory.', file=sys.stderr)
            return 1

    overlays = prepare_overlays(edit_paths)
    overlay_paths = list(overlays.values())

    initial_hashes = compute_initial_hashes(overlay_paths)
    initial_snapshots = snapshot_directories(overlay_paths)

    cmd = build_docker_cmd(args.image, overlay_paths, args.command, args.user)
    ret = run_container(cmd)

    final_hashes = compute_final_hashes(overlay_paths)
    changes = diff_hashes(initial_hashes, final_hashes)
    final_snapshots = snapshot_directories(overlay_paths)
    file_changes = diff_snapshots(initial_snapshots, final_snapshots)

    cleanup_overlays(overlays)

    if changes:
        print('Directories changed during session:')
        for c in changes:
            print(' -', c)
        for path, files in file_changes.items():
            for f in files:
                print(f'   {path}/{f}')
    else:
        print('No changes detected.')
    return ret


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
