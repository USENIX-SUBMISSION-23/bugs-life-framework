import sys
from bci import cli
from bci.version_control.version_control import RepoState, RepoLineage


class ChromiumRepo:

    def __init__(self, path):
        # if not self.is_repo(path):
        #    raise AttributeError("Invalid Chromium repository: '%s'" % path)
        self.path = path
        if sys.platform == "darwin":
            self.os_name = "Mac"
        elif sys.platform in ("linux", "linux2"):
            self.os_name = "Linux"
        else:
            raise AttributeError("Your operating system is not supported")

    def checkout(self, commit_pos):
        commit_hash = self.get_commit_hash(commit_pos)
        status = cli.execute_and_return_status("git checkout %s" % commit_hash, cwd=self.path)
        return status

    def get_commit_hash(self, commit_pos):
        output = cli.execute_and_return_output("git crrev-parse %s" % commit_pos, cwd=self.path)
        return output

    def get_commit_pos_lineage(self, ancestor_commit_pos, descendant_commit_pos):
        raise NotImplementedError()

    @staticmethod
    def is_repo(path):
        command = "git -C %s rev-parse --is-inside-work-tree" % path
        status = cli.execute_and_return_status(command)
        return status == 0


class ChromiumRepoState(RepoState):
    pass


class ChromiumRepoLineage(RepoLineage):

    def __init__(self, commit_pos_list, evaluation_targets=None):
        super().__init__()
        self.commit_pos_list = commit_pos_list
        self.states = []
        self.generate_state_lineage(evaluation_targets)

    def generate_state_lineage(self, evaluation_targets):
        self.states = ChromiumRepoState.create_state_list(evaluation_targets, self.commit_pos_list)
        self.ancestor_state = self.states[0]
        self.descendant_state = self.states[len(self.states) - 1]

    @property
    def length(self):
        return len(self.commit_pos_list)

    @property
    def state_ids_are_sequential(self):
        return True
