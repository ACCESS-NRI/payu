# coding: utf-8
"""
The payu interface for the ACCESS coupled climate model
-------------------------------------------------------------------------------
Contact: Marshall Ward <marshall.ward@anu.edu.au>
-------------------------------------------------------------------------------
Distributed as part of Payu, Copyright 2011 Marshall Ward
Licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""
from __future__ import print_function

# Standard Library
import errno
import os
import re
import shutil
import sys

# Extensions
import f90nml

# Local
from payu.fsops import make_symlink
from payu.models.model import Model
from payu.models.mom import get_restart_datetime_using_mom_submodel
import payu.calendar as cal


class Access(Model):

    def __init__(self, expt, name, config):
        super(Access, self).__init__(expt, name, config)

        self.model_type = 'access'

        self.cpl_keys = {'cice': ('input_ice.nml', 'coupling', 'runtime0'),
                         'matm': ('input_atm.nml', 'coupling', 'truntime0')}

        for model in self.expt.models:
            if model.model_type == 'cice' or model.model_type == 'cice5':
                model.config_files = ['cice_in.nml',
                                      'input_ice.nml']
                model.optional_config_files = ['input_ice_gfdl.nml',
                                               'input_ice_monin.nml']

                model.ice_nml_fname = 'cice_in.nml'

                model.access_restarts = ['mice.nc']
                model.copy_restarts = True

                model.set_timestep = model.set_access_timestep
                model.get_ptr_restart_dir = model.get_access_ptr_restart_dir

            if model.model_type == 'cice5':
                model.access_restarts.append(['u_star.nc', 'sicemass.nc'])

    def setup(self):
        if not self.top_level_model:
            return


        # Keep track of this in order to set the oasis runtime.
        run_runtime = 0

        for model in self.expt.models:

            if model.model_type == 'cice' or model.model_type == 'cice5':

                # Horrible hack to make a link to o2i.nc in the
                # work/ice/RESTART directory
                f_name = 'o2i.nc'
                f_src = os.path.join(model.work_path, f_name)
                f_dst = os.path.join(model.work_restart_path, f_name)

                if os.path.isfile(f_src):
                    make_symlink(f_src, f_dst)

            if model.model_type == 'cice5':

                # Stage the supplemental input files
                if model.prior_restart_path:
                    for f_name in model.access_restarts:
                        f_src = os.path.join(model.prior_restart_path, f_name)
                        f_dst = os.path.join(model.work_input_path, f_name)

                        if os.path.isfile(f_src):
                            make_symlink(f_src, f_dst)

            if model.model_type in ('cice', 'matm'):

                # Update the supplemental OASIS namelists

                # cpl_nml is the coupling namelist located in the control directory
                cpl_fname, cpl_group, runtime0_key = self.cpl_keys[model.model_type]
                cpl_fpath = os.path.join(model.work_path, cpl_fname)
                cpl_nml = f90nml.read(cpl_fpath)

            

                # Which calendar are we using, noleap or Gregorian.
                caltype = cpl_nml[cpl_group]['caltype']

                # Get time info about the beginning of this run. We're
                # interested in:
                #   1. start date of run
                #   2. total runtime of all previous runs.
                if model.prior_restart_path and not self.expt.repeat_run:
                    
                    # Read the start date from the restart date namelist
                    start_date_fpath = os.path.join(
                        model.prior_restart_path,
                        "restart_date.nml"
                    )
                    

                    # TODO: Do we want backwards compatibility?
                    try:
                        start_date_nml = f90nml.read(start_date_fpath)[cpl_group]
                    except FileNotFoundError:
                        print(
                            "Missing restart date file for model "
                            f"{model.model_type}",
                            file=sys.stderr
                        )
                        raise
                    
                    # Experiment initialisation date
                    init_date = cal.int_to_date(
                        start_date_nml["init_date"]
                    )
                    # Total time previously simulated
                    total_runtime = int(
                        start_date_nml[runtime0_key] + start_date_nml['runtime']
                    )
                    run_start_date = cal.date_plus_seconds(init_date,
                                                           total_runtime,
                                                           caltype)

                    # TODO: If we want backwards compatibility make 
                    # necessary adjustments.

                    # prior_cpl_fpath = os.path.join(model.prior_restart_path,
                    #                                cpl_fname)

                    # # With later versions this file exists in the prior restart
                    # # path, but this was not always the case, so check, and if
                    # # not there use prior output path
                    # if not os.path.exists(prior_cpl_fpath):
                    #     print('payu: warning: {0} missing from prior restart '
                    #           'path; checking prior output.'.format(cpl_fname),
                    #           file=sys.stderr)
                    #     if not os.path.isdir(model.prior_output_path):
                    #         print('payu: error: No prior output path; '
                    #               'aborting run.')
                    #         sys.exit(errno.ENOENT)

                    #     prior_cpl_fpath = os.path.join(model.prior_output_path,
                    #                                    cpl_fname)

                    # try:
                    #     prior_cpl_nml = f90nml.read(prior_cpl_fpath)
                    # except IOError as exc:
                    #     if exc.errno == errno.ENOENT:
                    #         print('payu: error: {0} does not exist; aborting.'
                    #               ''.format(prior_cpl_fpath), file=sys.stderr)
                    #         sys.exit(exc.errno)
                    #     else:
                    #         raise

                else:
                    init_date = cal.int_to_date(cpl_nml[cpl_group]['init_date'])
                    total_runtime = 0
                    run_start_date = init_date

                # Get new runtime for this run. We get this from either the
                # 'runtime' part of the payu config, or from the namelist
                if self.expt.runtime:
                    run_runtime = cal.runtime_from_date(
                        run_start_date,
                        self.expt.runtime['years'],
                        self.expt.runtime['months'],
                        self.expt.runtime['days'],
                        self.expt.runtime.get('seconds', 0),
                        caltype)
                else:
                    run_runtime = cpl_nml[cpl_group]['runtime']

                # Now write out new run start date and total runtime.
                cpl_nml[cpl_group]['inidate'] = cal.date_to_int(run_start_date)
                cpl_nml[cpl_group][runtime0_key] = total_runtime
                cpl_nml[cpl_group]['runtime'] = int(run_runtime)

                if model.model_type == 'cice':
                    if self.expt.counter and not self.expt.repeat_run:
                        cpl_nml[cpl_group]['jobnum'] = 1 + self.expt.counter
                    else:
                        cpl_nml[cpl_group]['jobnum'] = 1

                nml_work_path = os.path.join(model.work_path, cpl_fname)

                #TODO: Why is the following split into two steps?
                f90nml.write(cpl_nml, nml_work_path + '~')
                shutil.move(nml_work_path + '~', nml_work_path)

        # Now change the oasis runtime. This needs to be done after the others.
        for model in self.expt.models:
            if model.model_type == 'oasis':
                namcouple = os.path.join(model.work_path, 'namcouple')

                s = ''
                with open(namcouple, 'r+') as f:
                    s = f.read()
                    m = re.search(r"^[ \t]*\$RUNTIME.*?^[ \t]*(\d+)", s,
                                  re.MULTILINE | re.DOTALL)
                    assert(m is not None)
                    s = s[:m.start(1)] + str(run_runtime) + s[m.end(1):]

                with open(namcouple, 'w') as f:
                    f.write(s)

    def archive(self):
        if not self.top_level_model:
            return

        cice5 = None
        mom = None

        for model in self.expt.models:
            if model.model_type == 'cice':

                # Copy supplemental restart files to RESTART path
                for f_name in model.access_restarts:
                    f_src = os.path.join(model.work_path, f_name)
                    f_dst = os.path.join(model.restart_path, f_name)

                    if os.path.exists(f_src):
                        shutil.move(f_src, f_dst)

                # Copy configs from work path to restart
                for f_name in model.config_files:
                    f_src = os.path.join(model.work_path, f_name)
                    f_dst = os.path.join(model.restart_path, f_name)

                    if os.path.exists(f_src):
                        shutil.copy2(f_src, f_dst)
            
            if model.model_type in ('cice', 'matm'):
                
                # Write the end date to the restart date namelist
                cpl_fname, cpl_group, runtime0_key = self.cpl_keys[model.model_type]
                completed_run_cpl_nml_path = os.path.join(model.work_path, cpl_fname)
                completed_run_cpl_nml = f90nml.read(
                    completed_run_cpl_nml_path
                    )[cpl_group]
                
                completed_run_start_date = cal.int_to_date(
                    completed_run_cpl_nml["inidate"])
                
                completed_run_runtime = completed_run_cpl_nml["runtime"]
                caltype = completed_run_cpl_nml['caltype']

                completed_run_end_date = cal.date_plus_seconds(
                    completed_run_start_date,
                    completed_run_runtime,
                    caltype)
                
                end_date_nml = {
                    cpl_group: {
                        # Experiment initialisation date
                        "init_date": completed_run_cpl_nml["init_date"],
                        # Simulated time prior to completed simulation
                        runtime0_key: completed_run_cpl_nml[runtime0_key],
                        # Duration of completed simulation
                        "runtime": completed_run_cpl_nml["runtime"]
                    }
                }
                f90nml.write(
                    end_date_nml, 
                    os.path.join(model.restart_path, "restart_date.nml"),
                    force = True # Overwrite copy from previous restart
                )

            if model.model_type == 'cice5':
                cice5 = model
            elif model.model_type == 'mom':
                mom = model

        # Copy restart from ocean into ice area.
        if cice5 is not None and mom is not None:
            o2i_src = os.path.join(mom.work_path, 'o2i.nc')
            o2i_dst = os.path.join(cice5.restart_path, 'o2i.nc')
            shutil.copy2(o2i_src, o2i_dst)

    def get_restart_datetime(self, restart_path):
        """Given a restart path, parse the restart files and
        return a cftime datetime (for date-based restart pruning)"""
        return get_restart_datetime_using_mom_submodel(
            model=self, 
            restart_path=restart_path
        )

    def set_model_pathnames(self):
        pass

    def set_local_pathnames(self):
        pass

    def set_input_paths(self):
        pass

    def set_model_output_paths(self):
        pass

    def collate(self):
        pass
