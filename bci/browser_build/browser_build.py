import os
import json
import logging
from abc import abstractmethod
from bci import util
from bci.version_control.version_control import RepoState
from bci.browser_build.artisanal_build_manager import ArtisanalBuildManager


class BrowserBuild:

    def __init__(self, repo_path, bin_folder_path, data_folder_path, driver_folder_path):
        # if not os.path.isdir(repo_path):
        #    raise AttributeError("Repo path is invalid: '%s'" % repo_path)
        self.repo_path = repo_path
        self.logger = logging.getLogger("bci")

        if not os.path.isdir(bin_folder_path):
            os.makedirs(bin_folder_path)
        self.bin_folder_path = bin_folder_path
        self.artisanal_bin_folder_path = os.path.join(self.bin_folder_path, "artisanal")

        if not os.path.isdir(data_folder_path):
            os.makedirs(data_folder_path)
        self.data_folder_path = data_folder_path

        if not os.path.isdir(driver_folder_path):
            os.makedirs(driver_folder_path)
        self.driver_folder_path = driver_folder_path
        self.only_releases = False

        self.artisanal_build_manager = ArtisanalBuildManager(self)

    def set_only_releases(self, only_releases):
        self.only_releases = only_releases

    @property
    @abstractmethod
    def executable_name(self) -> str:
        pass

    @property
    @abstractmethod
    def browser_name(self) -> str:
        pass

    def list_downloaded_binaries(self):
        binaries = []
        for subfolder_path in os.listdir(os.path.join(self.bin_folder_path, "downloaded")):
            bin_entry = {}
            bin_entry["id"] = subfolder_path
            binaries.append(bin_entry)
        return binaries

    def update_artisanal_binaries_meta_data(self):
        self.artisanal_build_manager.update()

    def list_artisanal_binaries(self):
        return self.artisanal_build_manager.get_artisanal_binaries_list()

    @staticmethod
    def preferred_binary_representation(state_id):
        return state_id

    def build(self, state: RepoState):
        # Check cache
        if self.is_built(state):
            pass
        # Try to download snapshot
        elif self.has_available_snapshot_online(state.id):
            self.download_snapshot(state=state)
        else:
            return False
        self.post_build_step(state)
        return True

    @abstractmethod
    def download_snapshot(self, state_id: int = None, state: RepoState = None):
        pass

    @abstractmethod
    def post_build_step(self, state):
        pass

    def is_available_locally_or_online(self, state_id):
        return self.has_available_snapshot_locally(state_id) or self.has_available_snapshot_online(state_id)

    def has_available_snapshot_locally(self, state_id):
        bin_path = self.get_bin_path_from_id(state_id)
        return bin_path is not None

    @abstractmethod
    def has_available_snapshot_online(self, state_id):
        pass

    def is_built(self, state):
        bin_path = self.get_bin_path(state)
        return bin_path is not None

    def get_bin_path(self, state):
        """
        Returns path to binary, only if the binary is available locally. Otherwise it returns None.
        """
        return self.get_bin_path_from_id(state.id)

    def get_bin_path_from_id(self, build_id):
        """
        Returns path to binary, only if the binary is available locally. Otherwise it returns None.
        """
        path_downloaded = self.get_potential_bin_path(build_id)
        path_artisanal = self.get_potential_bin_path(build_id, artisanal=True)
        if os.path.isfile(path_downloaded):
            return path_downloaded
        if os.path.isfile(path_artisanal):
            return path_artisanal
        return None

    def get_potential_bin_path(self, build_id, artisanal=False):
        """
        Returns path to potential binary. It does not guarantee whether the binary is available locally.
        """
        if artisanal:
            return os.path.join(self.bin_folder_path, "artisanal", str(build_id), self.executable_name)
        return os.path.join(self.bin_folder_path, "downloaded", str(build_id), self.executable_name)

    def get_bin_folder_path(self, build_id):
        path_downloaded = self.get_potential_bin_folder_path(build_id)
        path_artisanal = self.get_potential_bin_folder_path(build_id, artisanal=True)
        if os.path.isdir(path_downloaded):
            return path_downloaded
        if os.path.isdir(path_artisanal):
            return path_artisanal
        return None

    def get_potential_bin_folder_path(self, build_id, artisanal=False):
        if artisanal:
            return os.path.join(self.bin_folder_path, "artisanal", str(build_id))
        return os.path.join(self.bin_folder_path, "downloaded", str(build_id))

    def remove_bin_folder(self, build_id):
        path = self.get_bin_folder_path(build_id)
        if path and "artisanal" not in path:
            if not util.rmtree(path):
                self.log_error("Could not remove folder '%s'" % path)

    @abstractmethod
    def get_driver_version(self, browser_version):
        pass


class BuildNotAvailableError(Exception):

    def __init__(self, browser_name, build_state):
        super().__init__("Browser build not available: %s (%s)" % (browser_name, build_state))
