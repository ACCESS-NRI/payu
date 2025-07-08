import copy
import datetime
import os
import shutil

import cftime
import f90nml
import pytest

import payu

from test.common import cd, expt_workdir
from test.common import tmpdir, ctrldir, labdir, workdir, expt_archive_dir, ctrldir_basename
from test.common import config as config_orig
from test.common import write_config
from test.common import make_all_files
from test.common import config_path
from test.common import list_expt_archive_dirs, remove_expt_archive_dirs

from test.models.test_cice5 import make_cice5_restart_dir
from test.models.test_mom_mixin import make_ocean_restart_dir
from test.models.test_um import make_atmosphere_restart_dir

from payu.calendar import GREGORIAN, NOLEAP
verbose = True

INPUT_ICE_FNAME = "input_ice.nml"

def setup_module(module):
    """
    Put any test-wide setup code in here, e.g. creating test files
    """
    if verbose:
        print("setup_module      module:%s" % module.__name__)

    # Should be taken care of by teardown, in case remnants lying around
    try:
        shutil.rmtree(tmpdir)
    except FileNotFoundError:
        pass

    try:
        tmpdir.mkdir()
        labdir.mkdir()
        ctrldir.mkdir()
        expt_archive_dir.mkdir(parents=True)
        make_all_files()
    except Exception as e:
        print(e)

CICE5_CONFIG = {
    "laboratory": "lab",
    "jobname": "testrun",
    "model": "access-esm1.6",
    "submodels": [{"name": "atmosphere",
                  "model": "um"},
                  {"name": "ocean",
                  "model": "mom"},
                  {"name": "ice",
                  "model": "cice5"}],
    "exe": "test.exe",
    "experiment": ctrldir_basename,
    "metadata": {"enable": False}
}


@pytest.fixture
def config(request):
    """
    Write a specified dictionary to config.yaml.
    Used to allow writing configs with and without
    restarts.
    """
    config = request.param
    write_config(config, config_path)

    yield config_path

    os.remove(config_path)


def teardown_module(module):
    """
    Put any test-wide teardown code in here, e.g. removing test outputs
    """
    if verbose:
        print("teardown_module   module:%s" % module.__name__)

    try:
        shutil.rmtree(tmpdir)
        print('removing tmp')
    except Exception as e:
        print(e)


@pytest.fixture(autouse=True)
def empty_workdir():
    """
    Model setup tests require a clean work directory and symlink from
    the control directory.
    """
    expt_workdir.mkdir(parents=True)
    # Symlink must exist for setup to use correct locations
    workdir.symlink_to(expt_workdir)

    yield expt_workdir
    try:
        shutil.rmtree(expt_workdir)
    except FileNotFoundError:
        pass
    workdir.unlink()

@pytest.fixture(autouse=True)
def teardown():
    # Run test
    yield

    # Remove any created restart files
    remove_expt_archive_dirs(type='restart')


@pytest.fixture
def esm1p6_um_only_config():
    """
    Configuration for experiment with UM as a submodel
    of ESM1.6
    """
    config = copy.deepcopy(config_orig)
    config["model"] = "access-esm1.6"
    config["submodels"] = [{"name": "atmosphere",
                           "model": "um"}]
    write_config(config)

    # Run test
    yield

    # Teardown
    os.remove(config_path)


@pytest.fixture
def ice_control_directory():
    # Make a cice control subdirectory
    ice_ctrl_dir = ctrldir / "ice"
    ice_ctrl_dir.mkdir()

    # Run test
    yield ice_ctrl_dir

    # Teardown
    shutil.rmtree(ice_ctrl_dir)


@pytest.fixture
def default_input_ice(ice_control_directory):
    # Create base input_ice.nml namelist as needed for setup
    ctrl_input_ice_path = ice_control_directory / INPUT_ICE_FNAME

    default_input_nml = {
        "coupling":
        {
            "jobnum": 2,
        }
    }
    f90nml.write(default_input_nml, ctrl_input_ice_path)

    # Run test
    yield ctrl_input_ice_path

    # Teardown handled by ice_control_directory fixture


@pytest.fixture
def fake_cice_in(ice_control_directory):
    # Create a fake cice_in.nml file. This is irrelevant for the tests,
    # however is required to exist for the experiment initialisation.
    fake_cice_in_nml = {
        "setup_nml": {
            "restart_dir": "",
            "history_dir": ""
        },
        "grid_nml": {
            "grid_file": "",
            "kmt_file": ""
        }
    }
    fake_cice_in_path = ice_control_directory / "cice_in.nml"
    f90nml.write(fake_cice_in_nml, fake_cice_in_path)

    yield fake_cice_in_path

    # Teardown handled by ice_control_directory fixture

@pytest.fixture
def um_only_ctrl_dir():
    """
    Configuration for experiment with UM as standalone
    model
    """
    # First make a separate control directory for standalone UM experiment
    um_ctrl_dir = tmpdir/"um_only_ctrl"
    um_ctrl_dir.mkdir()

    config = copy.deepcopy(config_orig)
    config["model"] = "um"

    write_config(config, path=um_ctrl_dir/"config.yaml")

    # Run test
    yield um_ctrl_dir

    # Teardown
    shutil.rmtree(um_ctrl_dir)


def test_esm1p6_patch_optional_config_files(um_only_ctrl_dir,
                                            esm1p6_um_only_config):
    """
    Test that the access-esm1.6 driver correctly updates the UM
    configuration files.
    """
    # Initialise standalone UM model
    with cd(um_only_ctrl_dir):
        um_config_path = um_only_ctrl_dir / "config.yaml"
        um_lab = payu.laboratory.Laboratory(lab_path=str(labdir),
                                            config_path=um_config_path) 
        um_expt = payu.experiment.Experiment(um_lab, reproduce=False)

    um_standalone_model = um_expt.models[0]

    # Initialise ESM1.6 with UM submodel
    with cd(ctrldir):
        esm1p6_lab = payu.laboratory.Laboratory(lab_path=str(labdir))
        esm1p6_expt = payu.experiment.Experiment(esm1p6_lab, reproduce=False)

    for model in esm1p6_expt.models:
        if model.model_type == "um":
            esm1p6_um_model = model

    # Check there are no duplicate files from double initialisation
    assert (
        len(esm1p6_um_model.optional_config_files) ==
        len(set(esm1p6_um_model.optional_config_files))
    )

    # Check that esm1p6 driver added new config files compared
    # to the standalone UM.

    expected_files = ["soil.nml", "pft_params.nml"]
    assert (
        set(esm1p6_um_model.optional_config_files) ==
        set(um_standalone_model.optional_config_files).union(expected_files)
    )


@pytest.mark.parametrize("config",
                        [CICE5_CONFIG],
                        indirect=True)
@pytest.mark.parametrize("run_dt",
    [cftime.datetime(1, 1, 1, calendar="proleptic_gregorian"),
     cftime.datetime(999, 1, 1, calendar="proleptic_gregorian")]
)
def test_resdate_consistency(run_dt, config, fake_cice_in, default_input_ice):
    """
    Test that the ESM1.6 consistency date check passes when
    submodels use the same restart dates.
    """
    # Setup the restart files for each submodel
    make_cice5_restart_dir(run_dt,
                           additional_path="ice")
    start_dt = cftime.datetime(1, 1, 1, calendar="proleptic_gregorian")
    make_ocean_restart_dir(start_dt, run_dt,  additional_path="ocean")
    make_atmosphere_restart_dir(run_dt,
                                additional_path="atmosphere")

    # Initialise the experiment
    with cd(ctrldir):
        lab = payu.laboratory.Laboratory(lab_path=str(labdir))
        expt = payu.experiment.Experiment(lab, reproduce=False)
    for model in expt.models:
        if model.model_type == "cice5":
            cice5_model = model
    access_esm1p6_model = expt.model

    # Required for model setup
    expt.runtime = {"years": 1,
                    "months": 0,
                    "days": 0}

    # Overwrite cice model paths created during experiment initialisation.
    cice5_model.work_path = workdir

    # Setup requirements for the CICE5 model. Apply these manually
    # to avoid running the CICE5 setup
    shutil.copy(default_input_ice, cice5_model.work_path)
    cice5_model.caltype = GREGORIAN
    cice5_model.cal_str = "proleptic_gregorian"

    access_esm1p6_model.setup()


@pytest.mark.parametrize("config",
                         [CICE5_CONFIG],
                         indirect=True)
@pytest.mark.parametrize("cice_dt,um_dt,mom_dt",
    [
     (
        cftime.datetime(1, 1, 1, calendar="proleptic_gregorian"),
        cftime.datetime(1, 1, 1, calendar="proleptic_gregorian"),
        cftime.datetime(1, 1, 2, calendar="proleptic_gregorian")
     ),
     (
        cftime.datetime(5555, 7, 3, calendar="proleptic_gregorian"),
        cftime.datetime(5555, 7, 1, calendar="proleptic_gregorian"),
        cftime.datetime(5555, 7, 3, calendar="proleptic_gregorian")
     ),
     (
        cftime.datetime(101, 12, 29, calendar="proleptic_gregorian"),
        cftime.datetime(101, 11, 29, calendar="proleptic_gregorian"),
        cftime.datetime(101, 11, 29, calendar="proleptic_gregorian")
     ),
     ]
)
def test_resdate_inconsistent(cice_dt, um_dt, mom_dt, config, fake_cice_in, default_input_ice):
    """
    Test that the ESM1.6 consistency date check fails when given inconsistent
    dates.
    """
    # Setup the restart files for each submodel
    make_cice5_restart_dir(cice_dt,
                           additional_path="ice")
    start_dt = cftime.datetime(1, 1, 1, calendar="proleptic_gregorian")
    make_ocean_restart_dir(start_dt, mom_dt,  additional_path="ocean")
    make_atmosphere_restart_dir(um_dt,
                                additional_path="atmosphere")

    # Initialise the experiment
    with cd(ctrldir):
        lab = payu.laboratory.Laboratory(lab_path=str(labdir))
        expt = payu.experiment.Experiment(lab, reproduce=False)
    for model in expt.models:
        if model.model_type == "cice5":
            cice5_model = model
    access_esm1p6_model = expt.model

    # Required for model setup
    expt.runtime = {"years": 1,
                    "months": 0,
                    "days": 0}

    # Overwrite cice model paths created during experiment initialisation.
    cice5_model.work_path = workdir

    # Setup requirements for the CICE5 model. Apply these manually
    # to avoid running the CICE5 setup
    shutil.copy(default_input_ice, cice5_model.work_path)
    cice5_model.caltype = GREGORIAN
    cice5_model.cal_str = "proleptic_gregorian"

    with pytest.raises(RuntimeError, match="Inconsistent dates"):
        access_esm1p6_model.setup()
