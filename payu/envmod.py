# coding: utf-8
"""envmodules
   ==========

   A modular port of the Environment Modules Python ``init`` script
"""

import os
import shlex
import subprocess

# Python 2.6 subprocess.check_output support
if not hasattr(subprocess, 'check_output'):
    from backports import check_output
    subprocess.check_output = check_output

DEFAULT_BASEPATH = '/opt/Modules'
DEFAULT_VERSION = 'v4.3.0'

MODULE_NOT_FOUND_HELP = """ To fix module not being found:
- Check module name and version in config.yaml (listed under `modules: load:`)
- If module is found in a module directory, ensure this path is listed in
config.yaml under `modules: use:`, or run `module use` command prior to running
payu commands.
"""

MULTIPLE_MODULES_HELP = """ To fix having multiple modules available:
- Add version to the module in config.yaml (under `modules: load:`)
- Modify module directories in config.yaml (under `modules: use:`)
- Or modify module directories in user environment by using module use/unuse
commands, e.g.:
    $ module use dir # Add dir to $MODULEPATH
    $ module unuse dir # Remove dir from $MODULEPATH
"""


def setup(basepath=DEFAULT_BASEPATH):
    """Set the environment modules used by the Environment Module system."""

    module_version = os.environ.get('MODULE_VERSION', DEFAULT_VERSION)

    moduleshome = os.environ.get('MODULESHOME', None)

    if moduleshome is None:
        moduleshome = os.path.join(basepath, module_version)

    # Abort if MODULESHOME does not exist
    if not os.path.isdir(moduleshome):
        print('payu: warning: MODULESHOME does not exist; disabling '
              'environment modules.')
        try:
            del(os.environ['MODULESHOME'])
        except KeyError:
            pass
        return
    else:
        print('payu: Found modules in {}'.format(moduleshome))

    os.environ['MODULE_VERSION'] = module_version
    os.environ['MODULE_VERSION_STACK'] = module_version
    os.environ['MODULESHOME'] = moduleshome

    if 'MODULEPATH' not in os.environ:
        module_initpath = os.path.join(moduleshome, 'init', '.modulespath')
        with open(module_initpath) as initpaths:
            modpaths = [
                line.partition('#')[0].strip()
                for line in initpaths.readlines() if not line.startswith('#')
            ]

        os.environ['MODULEPATH'] = ':'.join(modpaths)

    os.environ['LOADEDMODULES'] = os.environ.get('LOADEDMODULES', '')

    # Environment modules with certain characters will cause corruption
    # when MPI jobs get launched on other nodes (possibly a PBS issue).
    #
    # Bash processes obscure the issue at NCI, since it occurs in an
    # environment module function, and bash moves those to the end of
    # the environment variable list.
    #
    # NCI's mpirun wrapper is a bash script, and therefore "fixes" by doing
    # the shuffle and limiting the damage to other bash functions, but some
    # wrappers (e.g. OpenMPI 2.1.x) may not be present.  So we manually patch
    # the problematic variable here.  But a more general solution would be nice
    # someday.

    if 'BASH_FUNC_module()' in os.environ:
        bash_func_module = os.environ['BASH_FUNC_module()']
        os.environ['BASH_FUNC_module()'] = bash_func_module.replace('\n', ';')


def module(command, *args):
    """Run the modulecmd tool and use its Python-formatted output to set the
    environment variables."""

    if 'MODULESHOME' not in os.environ:
        print('payu: warning: No Environment Modules found; skipping {0} call.'
              ''.format(command))
        return

    modulecmd = ('{0}/bin/modulecmd'.format(os.environ['MODULESHOME']))

    cmd = '{0} python {1} {2}'.format(modulecmd, command, ' '.join(args))

    envs, _ = subprocess.Popen(shlex.split(cmd),
                               stdout=subprocess.PIPE).communicate()
    exec(envs)


def lib_update(required_libs, lib_name):
    # Local import to avoid reversion interference
    # TODO: Bad design, fixme!
    # NOTE: We may be able to move this now that reversion is going away
    from payu import fsops

    for lib_filename, lib_path in required_libs.items():
        if lib_filename.startswith(lib_name) and lib_path.startswith('/apps/'): 
            # Load nci's /apps/ version of module if required 
            # pylint: disable=unbalanced-tuple-unpacking
            mod_name, mod_version = fsops.splitpath(lib_path)[2:4]

            module('unload', mod_name)
            module('load', os.path.join(mod_name, mod_version))
            return '{0}/{1}'.format(mod_name, mod_version)

    # If there are no libraries, return an empty string
    return ''


def setup_user_modules(user_modules, user_modulepaths):
    """Run module use + load commands for user-defined modules"""

    if 'MODULESHOME' not in os.environ:
        print(
            'payu: warning: No Environment Modules found; ' +
            'skipping running module use/load commands for any module ' +
            'directories/modulefiles defined in config.yaml')
        return

    # Add user-defined directories to MODULEPATH
    for modulepath in user_modulepaths:
        if not os.path.isdir(modulepath):
            raise ValueError(
                f"Module directory is not found: {modulepath}" +
                "\n Check paths listed under `modules: use:` in config.yaml")

        module('use', modulepath)

    for modulefile in user_modules:
        # Check module exists and there is not multiple available
        module_subcommand = f"avail --terse {modulefile}"
        output = run_cmd(module_cmd(module_subcommand)).stderr

        # Extract out the modulefiles available
        modules = [line for line in output.strip().splitlines()
                   if not (line.startswith('/') and line.endswith(':'))]

        if len(modules) > 1:
            # Modules are used for finding model executable paths - so check
            # for unique module -TODO: Could be a warning rather than an error?
            raise ValueError(
                f"There are multiple modules available for {modulefile}:\n" +
                f"{output}\n{MULTIPLE_MODULES_HELP}")
        elif len(modules) == 0:
            raise ValueError(
                f"Module is not found: {modulefile}\n{MODULE_NOT_FOUND_HELP}"
            )

        # Load module
        module('load', modulefile)


def env_var_set_by_modules(user_modules, env_var):
    """Return an environment variable post loading only user-defined modules
    - this is used for getting $PATH for searching for the model executable"""
    if 'MODULESHOME' not in os.environ:
        print('payu: warning: No Environment Modules found; skipping '
              f'inspecting user module changes to ${env_var}')
        return

    # Note: Using subprocess shell to isolate changes to environment
    load_commands = [f'load {module}' for module in user_modules]
    commands = ['purge'] + load_commands
    module_cmds = [f"eval `{module_cmd(c)}`" for c in commands]
    module_cmds += [f'echo ${env_var}']
    command = ' && '.join(module_cmds)
    output = run_cmd(command)

    # Extract out $env_var from output
    output.check_returncode()
    lines = output.stdout.strip().split('\n')
    return lines[-1]


def module_cmd(command):
    """Format module subcommand using modulecmd"""
    return f"{os.environ['MODULESHOME']}/bin/modulecmd bash {command}"


def run_cmd(command):
    """Wrapper around subprocess command that captures output"""
    return subprocess.run(command, shell=True, text=True, capture_output=True)
