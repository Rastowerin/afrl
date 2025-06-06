# afrl

This repository contains a sample Python utility `sandbox_launcher.py` that demonstrates how to launch a highly restricted sandbox environment for local development.

The tool uses Docker with the gVisor runtime to create a container without network access and with a read-only filesystem. Directories specified with `--edit` are copied to temporary overlays so any modifications do not affect the originals. After the container exits the utility reports any files that were modified inside the overlays and cleans them up.

## Usage

```
python3 sandbox_launcher.py --image <docker-image> --edit <path1> --edit <path2> [--user dev] -- <command>
```

Example:

```
python3 sandbox_launcher.py --image alpine:latest --edit /workspace/project --user dev -- /bin/sh
```

This will start a sandboxed shell where only `/workspace/project` is writable via an overlay. Changes to that directory are detected after the container exits and the temporary overlay is removed.
