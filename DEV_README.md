# Payu code overview

## Development Setup

### Setting up a payu fork

There is a shared `access-nri/payu` repository fork for development work. This can be found at: https://github.com/ACCESS-NRI/payu.
The fork is used for storing and sharing git branches within the organisation. All Pull Requests and Issues are created in the upstream `payu-org/payu`
repository: https://github.com/payu-org/payu.

1. Log onto Gadi
2. Clone the fork somewhere in your home directory. E.g.

```bash
# Create and change into a new directory 
mkdir ~/payu_development 
cd ~/payu_development 

# Clone fork repository
git clone git@github.com:ACCESS-NRI/payu.git payu_fork
```

Note the above requires ssh authentication keys for github to be accessible on Gadi:
- Adding a SSH key to your github account: https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account
- Setting up SSH config to forward keys to Gadi: https://docs.access-hive.org.au/getting_started/set_up_nci_account/#createupdate-the-ssh-config-file

3. Change to the `master` branch (as the default on the fork is `access-nri`)

```bash
# Change directory to fork repository
cd payu_fork
git checkout master
```

4. Set an upstream remote, so we can get code updates from `payu-org/payu`.

```bash
# Add payu-org/payu as a remote
git remote add upstream git@github.com:payu-org/payu.git

# Check remotes:
git remote -v
# Expected output:
# origin git@github.com:ACCESS-NRI/payu.git (fetch)
# origin git@github.com:ACCESS-NRI/payu.git (push)
# upstream git@github.com:payu-org/payu.git (fetch)
# upstream git@github.com:payu-org/payu.git (push)
```

5. Fetch changes from payu-org/payu and update the `master` branch

```bash
git fetch upstream
git merge upstream/master

# Display the history of the commits - see that the latest is the same as payu-org/payu's master branch: https://github.com/payu-org/payu/commits/master/
git log
```

A useful reference for working with forks and pull request workflows: https://gist.github.com/Chaser324/ce0505fbed06b947d962 

### Creating a development environment

Python virtual environments are useful for creating isolated installs of payu, that can be easily updated, deleted and recreated. Python virtual environments also use fewer inodes than conda environments. 

1. Load a NCI python module

```bash
module load python3/3.11.0
```

2. Create an empty python virtual environment. It is best to not install them in the `$HOME` directory, as the environments can contain a number of small files, and would quickly add to filesystems quotas. Installing on `/scratch` is useful because if you do forget to clean up the environment, the environment will get deleted eventually.

```bash
# Replace project and user, or use a completely different path!
python3 -m venv /scratch/$PROJECT/$USER/payu-venv
```

3. Activate the environment

```bash
source /scratch/$PROJECT/$USER/payu-venv/bin/activate

# Check the python points to the environment
which python 
# Expected Output (using above example):
# /scratch/<your-project>/<your-userid>/payu-venv/bin/python
```

4. Install the payu fork in editable mode - this means any code changes are reflected in the install!

```bash
# Ensure the current directory is the payu fork repository, e.g. 
cd  ~/payu_development/payu_fork

# Install payu with `-e` for editable mode and `.` for current directory
pip install -e .

## Test the payu install:

which payu
# Expected output:
# /scratch/<your-project>/<your-userid>/payu-venv/bin/payu

payu --help
# Expected output:
# usage: payu [-h] [--version] {archive,branch,build,checkout,clone,collate,ghsetup,init,list,profile,push,run,setup,status,sweep,sync} ...

# positional arguments:
#   {archive,branch,build,checkout,clone,collate,ghsetup,init,list,profile,push,run,setup,status,sweep,sync}

# options:
#   -h, --help            show this help message and exit
#   --version             show program's version number and exit

```

5. Once you are finished with a session, you can deactivate the environment:

```bash
deactivate

# To re-activate the environment in another session:
module load python3/3.11.0
source /scratch/$PROJECT/$USER/payu-venv/bin/activate
```

1. When you no longer need the environment, it can be useful to delete virtual environment directory, e.g. `/scratch/<project>/<user>/payu-venv`, to reduce the usage of file inodes.

### Using VS Code

Modifying the code on Gadi, can be easily done using VS Code using the [Remote - SSH extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh). When you are finished with a session, click the green "SSH connection status" box in the lower left corner. Then, in the input box that opens, select the "Close Remote Connection" option.


### Creating feature branches

1. Ensure the local fork repository is up-to-date:

```bash
# Ensure the current directory is the payu fork repository, e.g. 
cd  ~/payu_development/payu_fork

git checkout master
git fetch upstream
git merge upstream/master
```

2. Checkout a new feature branch

```bash
git checkout -b my-feature-branch
```

3. Add code changes to the branch and add commits.

4. Once changes are tested, push the feature branch to the `access-nri/payu` fork.

```bash
# For the first time, use the `-u`/`--set-upstream` flag to link the local repository to `origin`
git push -u origin my-feature-branch

# For subsequent pushes
git push
```

5. Open PR in `payu-org/payu` repository. This can be done via the Github Web Interface by going to the [`access-nri/payu` fork](https://github.com/ACCESS-NRI/payu) and finding the feature branch, and clicking the "Compare & Pull Request" button. Verify that the base repository is `payu-org/payu` and base branch is `master`.


### Testing with a small MOM6 configuration

To manually test non-model specific changes, there is a small MOM6 configuration that can be run on the login nodes with `payu-run`: https://github.com/aidanheerdegen/mom6_double_gyre.

```bash
# Clone repository
cd ~/payu_development 
git clone git@github.com:aidanheerdegen/mom6_double_gyre.git

# Change to configuration directory, and update config.yaml if needed, e.g. check project and shortpath,
# and change `queue: express` to `queue: normal` (to reduce cost of jobs)
cd mom6_double_gyre

# Test payu setup
payu setup

# Test payu run - this creates and submits a PBS job which runs `payu-run` on the compute nodes
payu sweep # Sweep clears away work directory and any log files
payu run

# Wait for job to complete
payu status
# Once job is completed, check Exit Status, and PBS standard output/error files

# To debug payu run locally, use `payu-run` directly
payu sweep 
payu-run 
```

## Payu Code

### Top-level structure

- `.github/`: Contains CI/CD workflows for automatic testing and deployment
- `docs/`: Files and configuration for read-the-docs: https://payu.readthedocs.io/en/latest/index.html
- `payu/`: Source code
- `test/`: Test code written using pytest
- `pyproject.toml`: Project configuration file which includes dependencies and entry point configuration.

### Source code components

Some key components:
- `models/`: Contains model drivers classes, e.g. model-specific configuration and set up and post-processing.
- `schedulers/`: Classes for PBS/Slurm schedulers - used submitting and querying jobs
- `subcommands/`: Entrypoints for sub commands, e.g. `payu run`, `payu-run`, `payu collate`
- `experiment.py`: The experiment class - stores the over-arching state of the payu workflow. Currently a **huge** file!

### Experiment stages

Stages

- Init:
- Setup:
    Create the `work` directories
    Generate manifests
- Run:
    Generates and runs the model run command, e.g. `mpirun`
- Archive:
    Output, and restart files are moved the `work` directory to the `archive` directory.

### Model Drivers

#TODO Add summary of model drivers


### Post-processing:

- Collate 
- Sync
- Telemetry