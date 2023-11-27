import shutil
import subprocess

import git
import pytest

from payu.git_utils import get_git_repository, get_git_user_info
from payu.git_utils import git_checkout_branch
from payu.git_utils import PayuBranchError, PayuGitWarning

from test.common import tmpdir


@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Create tmp directory
    try:
        tmpdir.mkdir()
    except Exception as e:
        print(e)

    yield

    # Remove tmp directory
    try:
        shutil.rmtree(tmpdir)
    except Exception as e:
        print(e)


def create_new_repo(repo_path):
    """Helper function to initialise a repo and create first commit"""
    repo = git.Repo.init(repo_path)
    init_file = repo_path / "init.txt"
    add_file_and_commit(repo, init_file)
    return repo


def add_file_and_commit(repo, file_path, commit_no=0):
    """Helper function to add a commit to repo"""
    file_path.touch()
    repo.index.add([file_path])
    repo.index.commit(f"Add commit {commit_no}")
    return repo


def test_get_git_repo_invalid_repo_initialise():
    invalid_repo_path = tmpdir / "invalidRepo"
    invalid_repo_path.mkdir()
    repo = get_git_repository(invalid_repo_path, initialise=True)
    assert not repo.bare


def test_get_git_repo_invalid_repo_catch_error():
    invalid_path = tmpdir / "invalidRepo"
    invalid_path.mkdir()
    expected_warning_msg = "Path is not a valid git repository: "
    expected_warning_msg += str(invalid_path)
    with pytest.warns(PayuGitWarning, match=expected_warning_msg):
        repo = get_git_repository(invalid_path, catch_error=True)
        assert repo is None


def test_get_git_user_info_no_config_set():
    # Testing this is tricky as don't want to remove any global configs for
    # name or email. Instead using assumption that key 'testKey-54321' is not
    # defined in the 'user' namespace.
    repo_path = tmpdir / "test_repo"
    create_new_repo(repo_path)
    value = get_git_user_info(repo_path, 'testKey-54321', 'test_value')
    assert value is None


def test_get_git_user_info_config_set():
    repo_path = tmpdir / "test_repo"
    create_new_repo(repo_path)
    try:
        # Set config that is local to temporary test repository only
        subprocess.run('git config user.name "TestUserName"',
                       check=True,
                       shell=True,
                       cwd=repo_path)
        print("User name set successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error setting user name: {e}")

    value = get_git_user_info(repo_path, 'name', 'test_value')

    assert value == 'TestUserName'


@pytest.mark.parametrize("ref", ["branch", "hash", None])
def test_git_checkout_new_branch_from_remote_ref(ref):
    # Setup
    remote_repo_path = tmpdir / 'remoteRepo'
    remote_repo = create_new_repo(remote_repo_path)
    main_branch = remote_repo.active_branch
    main_branch_hash = main_branch.object.hexsha

    # Create branch_1
    branch_1 = remote_repo.create_head("branch-1")
    remote_repo.git.checkout(branch_1)
    add_file_and_commit(remote_repo, (remote_repo_path / 'file'), commit_no=1)
    branch_1_hash = branch_1.object.hexsha

    assert main_branch_hash != branch_1_hash

    # Re-checkout main branch
    remote_repo.git.checkout(main_branch)

    # Clone repo
    cloned_repo_path = tmpdir / 'cloned_repo'
    cloned_repo = remote_repo.clone(cloned_repo_path)

    if ref == "hash":
        start_point = branch_1_hash
        expected_hash = branch_1_hash
    elif ref == "branch":
        start_point = "branch-1"
        expected_hash = branch_1_hash
    else:
        start_point = None
        expected_hash = main_branch_hash

    # Test startpoint being remote branch/hash/None
    git_checkout_branch(cloned_repo_path,
                        'branch-2',
                        new_branch=True,
                        start_point=start_point)

    current_branch = cloned_repo.active_branch
    current_hash = current_branch.object.hexsha
    assert str(current_branch) == 'branch-2'
    assert current_hash == expected_hash


def test_git_checkout_new_branch_existing():
    # Setup
    repo_path = tmpdir / 'remoteRepo'
    repo = create_new_repo(repo_path)
    existing_branch = repo.active_branch

    # Test create branch with existing branch
    with pytest.raises(PayuBranchError):
        git_checkout_branch(repo_path,
                            str(existing_branch),
                            new_branch=True)


def test_git_checkout_non_existent_branch():
    # Setup
    repo_path = tmpdir / 'remoteRepo'
    create_new_repo(repo_path)

    # Test create branch with  non-existent branch
    with pytest.raises(PayuBranchError):
        git_checkout_branch(repo_path, "Gibberish")


def test_git_checkout_existing_branch():
    # Setup
    remote_repo_path = tmpdir / 'remoteRepo'
    remote_repo = create_new_repo(remote_repo_path)
    main_branch = remote_repo.active_branch

    # Create branch_1
    branch_1 = remote_repo.create_head("branch-1")
    remote_repo.git.checkout(branch_1)
    add_file_and_commit(remote_repo, (remote_repo_path / 'file'), commit_no=1)
    branch_1_hash = branch_1.object.hexsha

    # Re-checkout main branch
    remote_repo.git.checkout(main_branch)

    # Clone repo
    cloned_repo_path = tmpdir / 'cloned_repo'
    cloned_repo = remote_repo.clone(cloned_repo_path)

    # Test checkout existing remote branch
    git_checkout_branch(cloned_repo_path,
                        'branch-1')

    current_branch = cloned_repo.active_branch
    current_hash = current_branch.object.hexsha
    assert str(current_branch) == 'branch-1'
    assert current_hash == branch_1_hash
