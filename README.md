# techhorizons

Tech Horizons Program

## Repo layout

| Path | What |
|---|---|
| `os/` | Tech Horizons OS — a minimal Alpine ISO that turns a recycled x86_64 laptop into a student's server and course home. See [os/README.md](os/README.md). |

## Building the OS

The ISO is built on a dedicated Alpine builder VM, never on a workstation:

```sh
./os/iso/build-on-vm.sh
```

Full build and test topology is in [os/docs/ARCHITECTURE.md](os/docs/ARCHITECTURE.md).
Built ISOs are published under [Releases](../../releases), not committed to the repo.
