"""Payu experiment UUID and metadata support

Generates and commit a new experiment uuid and updates/creates experiment
metadata

:copyright: Copyright 2011 Marshall Ward, see AUTHORS for details.
:license: Apache License, Version 2.0, see LICENSE for details.
"""

import warnings
from pathlib import Path
from typing import Optional, List

import shortuuid
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from payu.fsops import read_config
from payu.laboratory import Laboratory
from payu.git_utils import get_git_branch, get_git_user_info, git_commit

# A truncated uuid is used for branch-uuid aware experiment names
TRUNCATED_UUID_LENGTH = 5
METADATA_FILENAME = 'metadata.yaml'

USAGE_HELP = """
If this is a new experiment, create a new git branch by running:
    payu checkout -b NEW_BRANCH_NAME
where NEW_BRANCH_NAME is name of the new branch. This will generate a new
uuid, a branch-uuid aware experiment name and commit changes to the
metadata file.

Alternatively to generate a new uuid or experiment name on the current git
branch at the next payu setup or run command, remove the pre-existing 'uuid' or
'experiment' fields from the metadata file.

Note: Experiment names are the name used for work and archive directories
in the laboratory directory.
"""


class ExperimentMetadataError(Exception):
    """Class for experiment name exceptions"""
    def __init__(self, message="Invalid experiment name in metadata"):
        super().__init__(message)
        print(USAGE_HELP)


class MetadataWarning(Warning):
    pass


class Metadata:
    """
    Class to store/update/create metadata such as experiment uuid and name

    Parameters:
        lab : Laboratory
            The modules laboratory
        branch : str | None = None
            The git branch on which the experiment is run
        control_path : Path | None = None
            Path to where the experiment is configured and run. The default
            is set to the current working directory. This default is set in
            in fsops.read_config
        config_path : Path | None = None
            Configuration Path. The default is config.yaml in the current
            working directory. This is also set in fsop.read_config
    """

    def __init__(self,
                 lab: Laboratory,
                 config_path: Optional[Path] = None,
                 branch: Optional[str] = None,
                 control_path: Optional[Path] = None) -> None:
        self.lab = lab
        self.config = read_config(config_path)

        if control_path is None:
            control_path = Path(self.config.get('control_path'))
        self.control_path = control_path
        self.filepath = self.control_path / METADATA_FILENAME

        self.branch = branch

        self.base_experiment_name = self.config.get('experiment',
                                                    self.control_path.name)

        metadata = self.read_file()
        self.uuid = metadata.get('uuid', None)
        self.experiment_name = metadata.get('experiment', None)

    def read_file(self) -> CommentedMap:
        """Read metadata file - preserving orginal format if it exists"""
        metadata = CommentedMap()
        if self.filepath.exists():
            # Use default ruamel YAML to preserve comments and multi-line
            # strings
            metadata = YAML().load(self.filepath)
        return metadata

    def setup(self) -> None:
        """Create/update metadata if no uuid or experiment name, otherwise run
        checks on existing metadata"""
        if self.uuid is None:
            warnings.warn("No experiment uuid found in metadata. "
                          "Generating a new uuid", MetadataWarning)
            self.update_metadata()
        elif self.experiment_name is None:
            # Add an experiment name back into metadata
            warnings.warn("No experiment name found in metadata. "
                          "Generating a new experiment name.", MetadataWarning)
            self.update_metadata(set_only_experiment_name=True)

        self.check_experiment_name()

    def update_metadata(self, set_only_experiment_name: bool = False) -> None:
        """Create/Update metadata - uses legacy existing name if there's an
        existing local archive"""
        lab_archive_path = Path(self.lab.archive_path)
        archive_path = lab_archive_path / self.base_experiment_name

        if archive_path.exists():
            warnings.warn(
                f"Pre-existing archive found at: {archive_path}. "
                f"Experiment name will remain: {self.base_experiment_name}",
                MetadataWarning
            )
            if set_only_experiment_name:
                self.set_new_experiment_name(legacy=True)
            else:
                self.set_new_uuid(legacy=True)
        else:
            if set_only_experiment_name:
                self.set_new_experiment_name()
            else:
                self.set_new_uuid()

        # Update metadata file
        self.update_file()

    def check_experiment_name(self) -> None:
        """Check experiment name in metadata file"""
        truncated_uuid = self.uuid[:TRUNCATED_UUID_LENGTH]
        if self.experiment_name.endswith(truncated_uuid):
            # Branch-uuid aware experiment name
            metadata_experiment = self.experiment_name
            self.set_new_experiment_name()
            if self.experiment_name != metadata_experiment:
                warnings.warn(
                    "Either the branch name, the control directory, or the "
                    "configured 'experiment' value has changed.\n"
                    f"Experiment name in {METADATA_FILENAME}: "
                    f"{metadata_experiment}\nGenerated experiment name: "
                    f"{self.experiment_name}.",
                    MetadataWarning
                )
                raise ExperimentMetadataError()
        else:
            # Legacy experiment name
            if self.experiment_name != self.base_experiment_name:
                msg = f"Experiment name in {METADATA_FILENAME} does not match"
                if 'experiment' in self.config:
                    msg += " the configured 'experiment' value."
                else:
                    msg += " the control directory base name."
                warnings.warn(msg + f"{self.experiment_name} does not equal "
                              f"{self.base_experiment_name}",
                              MetadataWarning)
                raise ExperimentMetadataError()

    def set_new_experiment_name(self, legacy: bool = False) -> None:
        """Set a new experiment name - this is used for work and archive
        directories"""
        if legacy:
            # Experiment remains base experiment name
            self.experiment_name = self.base_experiment_name
            return

        if self.branch is None:
            self.branch = get_git_branch(self.control_path)

        # Add branch and a truncated uuid to experiment name
        truncated_uuid = self.uuid[:TRUNCATED_UUID_LENGTH]
        if self.branch is None or self.branch in ('main', 'master'):
            suffix = f'-{truncated_uuid}'
        else:
            suffix = f'-{self.branch}-{truncated_uuid}'

        self.experiment_name = self.base_experiment_name + suffix

    def set_new_uuid(self, legacy: bool = False) -> None:
        """Create a new uuid and set experiment name"""
        # Generate new uuid and experiment name
        self.uuid = generate_uuid()
        self.set_new_experiment_name(legacy=legacy)

        if legacy:
            return

        # Check experiment name is unique in local archive
        lab_archive_path = Path(self.lab.archive_path)
        if lab_archive_path.exists():
            local_experiments = [item for item in lab_archive_path.iterdir()
                                 if item.is_dir()]
            while self.experiment_name in local_experiments:
                # Generate a new id and experiment name
                self.uuid = generate_uuid()
                self.set_new_experiment_name()

    def update_file(self) -> None:
        """Write any updates to metadata file"""
        metadata = self.read_file()

        previous_uuid = metadata.get('uuid', None)
        if previous_uuid is not None and previous_uuid != self.uuid:
            metadata['previous_uuid'] = previous_uuid

        # Update uuid
        metadata['uuid'] = self.uuid

        # Add experiment name
        metadata['experiment'] = self.experiment_name

        # Update email/contact in metadata
        self.update_user_info(metadata=metadata,
                              metadata_key='contact',
                              config_key='name',
                              filler_values=['Your name',
                                             'Add your name here'])

        self.update_user_info(metadata=metadata,
                              metadata_key='email',
                              config_key='email',
                              filler_values=['you@example.com',
                                             'Add your email address here'])

        # Write updated metadata to file
        YAML().dump(metadata, self.filepath)

    def update_user_info(self, metadata: CommentedMap, metadata_key: str,
                         config_key: str, filler_values=List[str]):
        """Add user email/name to metadata - if defined and not already set
        in metadata"""
        example_value = filler_values[0]
        filler_values = {value.casefold() for value in filler_values}
        if (metadata_key not in metadata
                or metadata[metadata_key] is None
                or metadata[metadata_key].casefold() in filler_values):
            # Get config value from git
            value = get_git_user_info(repo_path=self.control_path,
                                      config_key=config_key,
                                      example_value=example_value)
            if value is not None:
                metadata[metadata_key] = value

    def commit_file(self) -> None:
        "Add a git commit for changes to metadata file, if file has changed"
        commit_message = f"Updated metadata. Experiment uuid: {self.uuid}"
        git_commit(repo_path=self.control_path,
                   commit_message=commit_message,
                   paths_to_commit=[self.filepath])

    def setup_new_experiment(self, legacy: bool = False) -> None:
        """Creates new uuid, creates/updates metadata file and
        commits file to git"""
        self.set_new_uuid(legacy)
        self.update_file()
        self.commit_file()


def generate_uuid() -> shortuuid.uuid:
    """Generate a new uuid"""
    return shortuuid.uuid()
