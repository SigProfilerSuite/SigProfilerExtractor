# SigProfilerExtractor Workbench on a server

The upstream Workbench (SigProfilerExtractor's browser app), run on a server and
used from the browser on your own computer: upload inputs, start runs, follow
them, explore results, download them. Two ways to run it:

- **Your own server** (a lab workstation, a cloud VM, a cluster with Apptainer):
  one command, from a Docker image. See below.
- **The UAlbany DGX cluster**: a SLURM job. See [On the DGX cluster](#on-the-dgx-cluster).

Either way you open a link with a token in it, like a Jupyter server's. The
token is the key to the app: anyone with the link can read your files and run
programs as you, so keep it private.

## Your own server

On the server, once, get the launcher: copy `gateway/spe-workbench` there, or
take it out of the image:

```bash
docker run --rm --entrypoint cat mishugeb/sigprofilerextractor-workbench \
  /opt/spe-workbench/spe-workbench > spe-workbench && chmod +x spe-workbench
```

Then:

```bash
./spe-workbench start
```

It downloads the image the first time (a few GB), starts the app, and prints
the link:

```
  Open this link in your browser (keep it private: it is the key to the app):

    http://myserver.example.edu:8765/?token=45abac...

  Port 8765 not reachable from your computer (firewall, off campus)? Run
  this on your computer, keep it open, and use the link with localhost ...
    ssh -N -L 8765:localhost:8765 you@myserver.example.edu
```

| Command | Does |
|---|---|
| `./spe-workbench start` | Start it and print the link |
| `./spe-workbench url` | Print the link again |
| `./spe-workbench status` | Is it running? |
| `./spe-workbench logs` | Follow its log |
| `./spe-workbench stop` | Stop it, and any run in progress |
| `./spe-workbench update` | Get the newest image and restart |
| `./spe-workbench new-token` | New link; the old one stops working |

Options for `start`: `--data DIR` (default `~/sigprofiler-workbench`),
`--port N` (default 8765), `--cpus N`, `--memory 64g`, `--no-gpu`,
`--image NAME`.

- **Engine**: Docker or Podman when you may run them, else Apptainer or
  Singularity (clusters usually allow these, not Docker). The app runs as you,
  so the files it writes are yours.
- **The link stays the same** across restarts and reboots (Docker restarts it
  with the server), so you can bookmark it. `new-token` changes it.
- **Your files**: uploads, results, reference genomes and run records go in
  the data folder. Your home folder is visible inside the app at the same
  paths, so you can paste a path such as `/home/you/project/vcfs` as it is.
- **GPU**: given to the app when the server has an NVIDIA GPU (Docker needs
  the NVIDIA container toolkit; without it, the app starts on the CPUs).
  Tick *Use the GPU* in a run's Advanced settings to use it.
- **CPUs**: runs use at most the CPUs the app has (`--cpus`, or all).

Without the launcher, the same with plain Docker:

```bash
docker run -d --name spe-workbench --restart unless-stopped -p 8765:8765 \
  --user "$(id -u):$(id -g)" -v "$HOME:$HOME" -e SPE_DATA="$HOME/sigprofiler-workbench" \
  -e SPE_HOST_NAME="$(hostname -f)" --gpus all mishugeb/sigprofilerextractor-workbench
docker logs spe-workbench        # shows the link
```

### Building and publishing the image

From this folder, on a machine with Docker:

```bash
docker build -t mishugeb/sigprofilerextractor-workbench .                         # GPU + CPU
docker build -t mishugeb/sigprofilerextractor-workbench:cpu --build-arg TORCH=cpu .  # smaller, CPU only
docker push mishugeb/sigprofilerextractor-workbench
```

`SPE_REF` (a build arg) picks the SigProfilerExtractor commit, tag or branch;
the default is the tested commit. The image holds SigProfilerExtractor as
published plus `gateway/`; data lives only in the mounted folder.

## What the app adds to the Workbench

- **Upload & download** (bottom-right button, or `/gateway/`): upload files or
  a folder, and copy the path to paste into the Workbench's Input card;
  download any run's output folder as one .zip. The Workbench's **Browse**
  buttons cannot open a file picker on a server, so paste paths instead.
- **The ready pill** in the top bar shows the CPUs and GPUs and live GPU use
  (`ready · 32 CPUs · 1 GPU (63% busy, 14/80 GB)`). Click it for graphs of CPU
  load, memory, and each GPU's load and memory over the last 10 minutes
  (sampled every 2 s, refreshed every 3 s while open). On the cluster it also
  shows the job, its time left and how full the node is. Memory is the working
  set: the job's or container's usage less reclaimable file cache.
- **CPU limits**: the Computer fields in Advanced settings are capped at the
  CPUs the app has, and a run asking for more is refused.

## On the DGX cluster

```bash
cd /network/rit/lab/islam_lab/mishu/sigprofiler_webapp
sbatch run_workbench.sbatch
cat workbench_endpoint.env      # WORKBENCH_URL=http://dgxNN.its.albany.edu:PORT/?token=...
```

Open `WORKBENCH_URL` on the campus network or VPN. Off campus without VPN,
tunnel with the **same port on both ends** (the job log prints the command),
then open `http://localhost:PORT/?token=...`:

```bash
ssh -N -L PORT:dgxNN.its.albany.edu:PORT si174851@dgx-head01.its.albany.edu
```

This uses the clone and venv in this folder rather than the image, with a new
token per job. Only one Workbench job can run at a time (a second one exits at
once): runs are tracked by process ID on their own node, in one shared records
folder. Stop with **Quit** in the Workbench, or `scancel -n spe_workbench`.
Runs live inside the job, so ending it stops any unfinished run; size `--time`
to fit.

## Layout

| Path | What |
|---|---|
| `gateway/spe_gateway.py` | The add-on: token sign-in, upload, .zip download, resources |
| `gateway/static/` | Its pages, script and styles |
| `gateway/spe-workbench` | Launcher for your own server |
| `gateway/entrypoint.sh` | The image's start-up script |
| `Dockerfile`, `.dockerignore` | The image |
| `run_workbench.sbatch` | The cluster job |
| `SigProfilerExtractor/` | Unmodified upstream clone (`git pull` to update), for the cluster job |
| `SigProfilerExtractor/.venv-dashboard/` | Its venv (git-ignored) |
| `uploads/`, `SigProfilerExtractor_results/` | The cluster job's uploads and results |
| `.cache/sigprofilerextractor/` | The cluster job's run records |
| `workbench_endpoint.env` | The cluster job's current URL and token (`chmod 600`) |
| `logs/` | Cluster job logs |

## How it fits with the local launcher

`gateway/spe_gateway.py` imports the Workbench's own server and handler; no
upstream file is changed. The Workbench answers only `127.0.0.1` and has no
login. The gateway listens on the server, admits only requests that carry the
token, then passes them to the Workbench as if they came from the server
itself, so its own checks still run.

`./launch_web.sh` in the clone still works as upstream intends, even while the
cluster job is running. Each keeps separate run records: the job's are under
`.cache/` here, the local launcher's under `~/.cache`. `--stop` on one does
not stop the other.

Two things to know about the clone's venv:

- **PyTorch was swapped for its CUDA 12.8 build** (the DGX driver, 570,
  predates CUDA 13). `./launch_web.sh --reinstall` puts the default CUDA 13
  build back, after which runs still work but cannot use the GPU. To restore:
  `.venv-dashboard/bin/python -m uv pip install --python .venv-dashboard/bin/python
  --reinstall-package torch torch --index-url https://download.pytorch.org/whl/cu128`
- **`./uninstall_web.sh` deletes `.venv-dashboard`**, which the job also uses.
  Recreate it with `./launch_web.sh --no-launch` (then the PyTorch step above).

## Security

The link's token grants everything the Workbench can do: read any file you
can, and run processes as you. Treat it like a password; `new-token` (or a new
cluster job) replaces it. The port is plain HTTP: on a network you do not
trust, use the SSH tunnel instead of opening the port.
