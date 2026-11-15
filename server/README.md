# Run the SigProfilerExtractor Workbench on a server or cluster

Run the Workbench (SigProfilerExtractor's browser app) on a Linux server (a lab
workstation, an HPC cluster, a cloud VM) and use it from the browser on your own
computer: upload inputs, start runs, follow them, explore results and download
them, the same way you use a Jupyter server.

- **No admin rights needed**: no `sudo`, no Docker, no system Python. One
  script, `spe-server`, installs everything into a folder of yours.
- **It runs as you**: each person starts their own copy, with their own link,
  files and runs.
- **GPUs**: it installs PyTorch's CUDA 12.8 build, which uses an NVIDIA GPU
  when there is one and the CPUs otherwise.
- **On a server or a cluster**: `start` runs it on the machine you are on;
  `submit` runs it as a SLURM job on a cluster's compute node
  ([which one?](#which-one-start-or-submit)).

You open a link with a token in it. The token is the key to the app: anyone
with the link can read your files on the server and run programs as you, so
keep it private.

## What you need

- A Linux server you can log in to with SSH (x86-64 or ARM).
- `bash`, `git`, `tar`, and `curl` or `wget`, which nearly every server has.
- Internet access from the server the first time, to github.com, pypi.org and
  download.pytorch.org. After that it can be offline.
- About 8 GB free for the install (2 GB with `--torch cpu`), plus room for
  results and any reference genomes (about 3 GB each). It asks for 20 GB free
  to start.

## Which one: `start` or `submit`?

The launcher runs the app in one of two ways. Pick by where you are logged in:

| | `./spe-server start` | `./spe-server submit` |
|---|---|---|
| **Use it on** | a machine you may run work on directly: a lab workstation, a cloud VM, an interactive session on a compute node | a cluster's login node, where SLURM (`sbatch`) runs the work |
| **Where the app runs** | on this machine, in the background | on a compute node SLURM picks, as a batch job |
| **CPUs, memory, GPUs** | this machine's, shared with anyone else on it (limit with `--cpus`) | only what the job asks for (`--cpus`, `--memory`, `--gpus`), its own |
| **How long it runs** | until `stop`, or until the machine restarts | until `stop` or the job's time limit (`--time`); a job may also wait in the queue first |
| **The link** | this machine's name | the compute node's name; the tunnel goes through the login node |

**On a cluster, use `submit` from the login node.** Login nodes are shared by
everyone for editing and submitting jobs; a fit running there slows them all,
and clusters often stop long or heavy processes on them. Run `start` on a
cluster only inside an interactive job on a compute node (for example
`srun --pty bash`), and then the app ends when that session ends.

Not sure? If `sbatch` exists (`command -v sbatch`) and the machine's name says
"login" or "head", use `submit`; otherwise use `start`. Either way, every other
command (`url`, `status`, `logs`, `stop`, ...) works the same, and the data
folder is the same, so you can switch between them: `stop` one, then run the
other.

## 1. Get the code

Log in to the server and clone the repository **on a disk with room**, such
as a lab or project share, not a small home folder. Your data goes in
`spe-data` next to the clone.

```bash
cd /path/with/room            # e.g. /lab/share/web_servers
git clone -b workbench-server https://github.com/SigProfilerSuite/SigProfilerExtractor.git
cd SigProfilerExtractor/server
```

## 2. Start it

```bash
./spe-server start
```

The first start downloads [uv](https://docs.astral.sh/uv/), which installs
Python 3.13, PyTorch and SigProfilerExtractor from this clone (several
minutes, once). Then it starts the app in the background and prints:

```
  SigProfilerExtractor Workbench is running on myserver.example.edu.

  Open this link in your browser (keep it private: it is the key to the app):

    http://myserver.example.edu:8765/?token=45abac...

  Not reachable from your computer (firewall, off campus, a cloud VM)? Run this on your
  computer, keep it open, and use the link with localhost in place of
  myserver.example.edu:

    ssh -N -L 8765:localhost:8765 you@myserver.example.edu

  Your files: /path/with/room/spe-data
```

On a cluster's login node, run `./spe-server submit` instead ([which
one?](#which-one-start-or-submit)): it installs the same way, then submits a
SLURM job that runs the app on a compute node, and prints the link once the job
has started ([on a SLURM cluster](#on-a-slurm-cluster) has the options).

## 3. Open it in your browser

**Try the link as printed first.** On campus or on the VPN it often just
works.

**If the page does not load** (it times out), the server's port is closed to
your computer. Make an SSH tunnel:

1. Open a terminal **on your own computer**: Terminal on a Mac, PowerShell on
   Windows 10 or 11 (both have `ssh`).
2. Paste the `ssh -N -L ...` command the launcher printed and log in as you
   normally do. It then shows nothing; that is right. Leave it open while you
   use the app.
3. Open the link with `localhost` in place of the server's name:
   `http://localhost:8765/?token=45abac...`

Print the link and the tunnel command again any time with `./spe-server url`.

## 4. Use it

The Workbench is the same as on your own computer, with these differences:

- **Choosing files on the server**: the **Choose** and **Browse** buttons open
  the Workbench's own file browser, which shows the server's folders (a
  window from your computer's system cannot show them). It starts in your
  home folder; the buttons along its top jump to **Home**, **Results**, the
  **Data folder** and **Uploads**. Open folders by clicking them, click
  **.. up one level** to go up, then click a file, or **Use this folder** for
  a folder. Folders holding results are marked *results*, and inputs are
  marked *calls*, *matrix* or *bedpe*. You can also paste a path on the
  server.
- **Inputs on your computer**: click **Upload** beside **Choose** in the Input
  card. For variant calls or BEDPE files, select all the files at once (they
  go into one folder); for a matrix or a segmentation file, select the one
  file. A bar shows the progress; the files land in a new folder in the data
  folder's `uploads/` (named like `vcf_20261114-153012`), and the Workbench
  then uses them as the input. Up to 8 GB per upload. For larger inputs,
  copy them to the server with `scp` or `rsync` and choose them there.
- **Results** are saved on the server, in the data folder's
  `SigProfilerExtractor_results/` unless you choose another output folder.
  Open a run's results and click **Download all as .zip** at the top: the
  server packs the folder first (it shows how many files and how much), then
  your browser downloads it. Single files have their own **Download**
  buttons.
- **GPU**: tick *Use the GPU* in a run's Advanced settings.

Closing the browser stops nothing: runs keep going, and the same link finds
them later, even from another computer. The app keeps running after you log
out of the server.

## 5. Stop it

```bash
./spe-server stop
```

This stops the app and any run in progress; so does **Quit** in the
Workbench's top bar. Start it again with `./spe-server start`; the link
stays the same. It does not come back by itself after the server restarts.

## On a SLURM cluster

Clone on a disk the compute nodes share (a lab or project share), then, on
the login node:

```bash
./spe-server submit --gpus 1 --cpus 32 --memory 128G --time 2-00:00:00 -- --partition=NAME
```

It installs on the login node first (compute nodes often have no internet),
submits a job that runs the Workbench, waits for the job to start, and prints
the link. Before submitting it shows exactly what the job asks for:

```
spe-server: submitting a SLURM job that asks for:
    CPUs     32                 given; change with --cpus N
    memory   128G               given; change with --memory SIZE (e.g. 64G)
    GPUs     1                  given; change with --gpus N
    time     2-00:00:00         given; change with --time T (e.g. 8:00:00, 2-00:00:00)
    other    --partition=NAME    (given; options after --)
  (each is remembered for the next submit)
```

### Asking for resources

The job holds what it asks for from the moment it starts until it ends,
whether a run is going or not. Every run you start in the Workbench runs
inside it and can use only that.

| You want | Option | Becomes (`sbatch`) | Default |
|---|---|---|---|
| CPUs | `--cpus N` | `--cpus-per-task N` | 8 |
| Memory | `--memory SIZE`, e.g. `64G`, `500M` | `--mem SIZE` (for the whole job) | 32G |
| GPUs | `--gpus N` | `--gres gpu:N` | 0: none |
| Time limit | `--time T`: `MM:SS`, `HH:MM:SS` or `D-HH:MM:SS` | `--time T` | the partition's default, which can be short: set it |
| Anything else | after `--`, as `sbatch` takes it: `--partition=NAME`, `--account=NAME`, `--qos=NAME`, `--constraint=...` | the same | none |

**How much to ask for:**

- **CPUs**: a run fits its NMF replicates in parallel, one per CPU (the
  Computer fields in Advanced settings use all of the job's CPUs unless you
  set fewer), so more CPUs make a run faster.
- **GPUs**: ask for one (`--gpus 1`) to use *Use the GPU* in a run's Advanced
  settings; without one the run uses the CPUs. Most clusters put GPUs in
  their own partition, so add it after `--`.
- **Memory**: grows with the number of samples, mutation contexts and CPUs. A
  safe start is about 4 GB per CPU (32 CPUs, 128G). Too little, and SLURM
  stops the job when it runs out (`OUT_OF_MEMORY` in `status`).
- **Time**: long enough for every run you plan, plus some margin. A small
  test (21 samples, 1 to 2 signatures, 3 replicates) took 2 minutes on 4 CPUs;
  a whole cohort with the defaults (1 to 25 signatures, 100 replicates) can
  take many hours. When the limit comes, the job ends and so does any run
  still going (the app is told a minute early, so it stops them cleanly).
- **Partition, account, QOS**: whatever your cluster requires. Many clusters
  refuse a job without `--account`, or put it in a default partition with a
  short time limit.

**Your cluster's limits:** `sinfo -o "%P %l %c %m %G"` lists each partition's
time limit, CPUs, memory and GPUs per node; `sacctmgr show qos
format=name,maxwall` the QOS limits; your cluster's documentation, which
accounts you have. Asking for more than a partition allows leaves the job
waiting forever or refused; asking for less makes it start sooner.

**Changing them later:** `./spe-server stop`, then `submit` again with the
new options. Options you leave out keep their last value, so
`./spe-server submit --time 1-00:00:00` changes only the time limit.

### Using the job

The other commands then work on the job: `url` prints the link (also once a
waiting job starts), `status` shows the node and the time left or why it is
still waiting, `logs` follows its log, and `stop` cancels it, stopping any
run first. `squeue -u $USER` shows it as `spe-server-<you>`.

Compute nodes are usually reachable only from inside the cluster, so the
printed tunnel goes through the login node:

```bash
ssh -N -L 8765:node12.cluster.edu:8765 you@login.cluster.edu
```

Run it on your computer, then open the link with `localhost` in place of the
node's name.

### On the UAlbany DGX cluster

From `dgx-head01`:

```bash
./spe-server submit --gpus 1 --cpus 32 --memory 128G --time 2-00:00:00 \
  -- --partition=dgx --qos=freetier
```

`freetier` allows up to 7 days but can be preempted by `paidtier-1` jobs;
`--qos=paidtier-1` is not preempted but allows at most 1 day.

## Commands

| Command | Does |
|---|---|
| `./spe-server start` | Start it and print the link |
| `./spe-server submit` | Run it as a SLURM job instead |
| `./spe-server url` | Print the link and the tunnel command again |
| `./spe-server status` | Is it running? (a job: where, and the time left) |
| `./spe-server logs` | Follow its log (Ctrl-C to leave; the app keeps running) |
| `./spe-server stop` | Stop it, and any run in progress |
| `./spe-server new-token` | New link; the old one stops working |
| `./spe-server update` | Reinstall from the clone and restart (`git pull` first) |
| `./spe-server install` | Install only (`start` does it when needed) |
| `./spe-server --help` | All of this, in the terminal |

## Options

None are needed. Each one you give is remembered for the next `start` or
`submit` on that server.

| Option | Default | Meaning |
|---|---|---|
| `--data DIR` | `spe-data` beside the clone | Where the install, uploads, results, genomes and run records go |
| `--port N` | 8765 | The port to try first; if it is taken, the next free one |
| `--cpus N` | all (`submit`: 8) | CPUs the runs may use; `all` removes a limit |
| `--no-gpu` | GPUs used | Hide the GPUs from the app; `--gpu` undoes it |
| `--torch BUILD` | `cu128` | PyTorch build: `cu128` (NVIDIA driver 525 or newer; also runs on CPUs) or `cpu` (6 GB smaller). Changing it reinstalls PyTorch |
| `--gpus N` | 0 | `submit` only: GPUs the job asks for |
| `--memory SIZE` | 32G | `submit` only: memory the job asks for |
| `--time T` | the partition's | `submit` only: the job's time limit, e.g. `2-00:00:00` |

## Good to know

- **Where your files go.** Everything is in the data folder: the install in
  `.workbench/install/`, uploads in `uploads/`, results in
  `SigProfilerExtractor_results/`, reference genomes in `references/`, run
  records in `.cache/`. In the clone, installing adds only files git ignores
  (`SigProfilerExtractor/_version.py`, `*.egg-info`); nothing large goes in
  your home folder.
- **One copy per data folder.** Run records are kept per data folder, and a
  run is tracked by its process on its own machine, so `start` and `submit`
  refuse while a copy for the same data folder runs anywhere, and say where.
- **Ports.** If someone else on the server already has 8765, the app takes the
  next free one and the link shows it. That port is tried first next time, so
  a bookmarked link keeps working.
- **CPUs.** Runs use at most the CPUs the app has: `--cpus`, a SLURM job's
  CPUs, or all. The Computer fields in Advanced settings are capped there, and
  a run asking for more is refused. On a shared server, leave room for others
  with `--cpus`.
- **Updating.** `git pull`, then `./spe-server stop` and `start` to run the
  new code; changed requirements are installed on that start. Or
  `./spe-server update`, which reinstalls everything and restarts.
  The launcher was called `spe-workbench` before; `spe-server` finds the
  same data folder, install and running app or job.
- **Two people on one server** each clone and start their own copy; they get
  different ports, tokens, files and runs.

## Troubleshooting

**"that disk has only N GB free"**: the data folder would be on a small disk,
such as a home folder. Give a folder on a larger one; it is remembered:
`./spe-server start --data /lab/share/spe-data`.

**"could not download ..." or "could not install PyTorch"**: the server cannot
reach the internet. If it uses a proxy, set `https_proxy` before starting. On
a cluster, install on the login node: `submit` does that, or run
`./spe-server install` there.

**The link does not load (it times out)**: use the SSH tunnel ([step 3](#3-open-it-in-your-browser)).

**"This site can't provide a secure connection" or `ERR_SSL_PROTOCOL_ERROR`**:
the browser switched the link to `https://`. The app speaks plain `http://`:
type the link with `http://` in front, or use the tunnel and `localhost`.

**The tunnel says "Address already in use"**: something on your own computer
has that port. Use another one on your side, for example
`ssh -N -L 9000:localhost:8765 you@myserver.example.edu`, then open
`http://localhost:9000/?token=...`.

**The page asks for a token**: paste the part of the link after `?token=`,
or open the whole link. After `new-token`, old links stop working.

**The ready pill shows no GPU**: on a cluster, ask for one (`--gpus 1`). On a
server, check that `nvidia-smi` lists it, and that `--no-gpu` is not set
(`--gpu` undoes it). A driver older than 525 cannot run the CUDA 12.8 build.

**A SLURM job keeps waiting**: `./spe-server status` shows why (the
reason SLURM gives). Ask for less (`--cpus`, `--memory`, `--gpus`, `--time`)
or another partition.

**The job ends at once**: `./spe-server logs` shows why. Often the cluster
requires an option, such as `-- --partition=NAME --account=NAME`, or the data
folder is not on a disk the compute nodes can see.

**A run in a job stops partway**: the job may have run out of memory or time,
or been preempted. Submit again with more `--memory` or `--time`, or a QOS
that is not preempted.

Anything else: `./spe-server logs` usually says what went wrong.

## On a cloud VM

- **Disk**: at least 30 GB for the install and a genome or two; more for data.
- **Machine**: CPUs matter most; an NVIDIA GPU speeds up runs with *Use the
  GPU*. Without one, `--torch cpu` saves 6 GB.
- **Reaching it**: keep the firewall closed and use an SSH tunnel. On Google
  Cloud: `gcloud compute ssh VM_NAME --zone ZONE -- -N -L 8765:localhost:8765`,
  then open `http://localhost:8765/?token=...`. The app speaks plain HTTP, so
  do not open its port to the internet: the token would cross it unencrypted.

## Security

The token grants everything the Workbench can do: read any file you can on
the server and run processes as you. Treat it like a password: do not paste
it in shared documents or chats. `./spe-server new-token` replaces it. The
port is plain HTTP, so on a network you do not trust, use the SSH tunnel
instead of opening the port.

## How it works

`gateway/spe_gateway.py` imports the Workbench's own server and handler. The
Workbench answers only `127.0.0.1` and has no login. The gateway listens on
the server, admits only requests that carry the token, then passes them to
the Workbench as if they came from the server itself, so its own checks still
run. It adds:

- **Files**: it tells the Workbench to draw its own file browser (no window
  from the server's system can reach your screen), to put uploads in the data
  folder's `uploads/`, and to start browsing in your home folder. The browser,
  upload and .zip download are the Workbench's own
  (`SigProfilerExtractor/web/files.py`), so they work the same everywhere.
- **The ready pill** in the top bar shows the CPUs and GPUs and live use
  (`ready · 32 CPUs · 1 GPU (63% busy, 14/80 GB)`). Click it for graphs of CPU
  load, memory, and each GPU's load and memory over the last 10 minutes. In a
  SLURM job it also shows the job, its time left and how full the node is.
- **CPU limits**, as above.

| Path in `server/` | What |
|---|---|
| `spe-server` | The launcher |
| `gateway/spe_gateway.py` | Token sign-in, free-port choice, file settings, resources |
| `gateway/static/` | The sign-in page's styles, and the resources panel's script and styles |
| `gateway/entrypoint.sh` | Start-up script the launcher runs, and its settings |

In the data folder, `.workbench/` holds the install, the token, the link, the
log and the last start's settings (`launch.env`).

The Workbench's own launcher, `../launch_web.sh`, is separate and still works
as upstream intends, with its own environment (`.venv-dashboard`) and run
records (`~/.cache`). Stopping one does not stop the other.
