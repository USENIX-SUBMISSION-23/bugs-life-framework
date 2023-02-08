import os
import shutil
import tarfile
import re
import requests
from bci import util
from bci import cli
from bci.browser_build.browser_build import BrowserBuild
from bci.version_control.firefox_vc import FirefoxRepo, FirefoxRepoState
from bci.data_storage.mongodb import MongoDB


class FirefoxBuild(BrowserBuild):

    def __init__(self, repo_path, bin_folder_path, data_folder_path, driver_folder_path):
        super().__init__(repo_path, bin_folder_path, data_folder_path, driver_folder_path)
        self.repo = FirefoxRepo(repo_path)
        self.update_available_snapshot_online_cache()

    def get_state_lineage_from_versions(self, lower_version, upper_version):
        lineage = self.repo.get_state_lineage_from_versions(lower_version, upper_version, self.only_releases)
        self.logger.info("Boundaries found: %s - %s" % (lineage.ancestor_state.id, lineage.descendant_state.id))
        self.logger.info("Of which %i are to be evaluated" % lineage.nb_of_states_to_be_evaluated)
        return self.repo.get_state_lineage_from_versions(lower_version, upper_version, self.only_releases)

    def get_release_tag(self, version):
        return self.repo.get_release_tag(version)

    def get_state_lineage_from_commit_positions(self, lower_revision_id, upper_revision_id):
        lower_changeset_id = self.repo.get_changeset_id_from_revision_id(lower_revision_id)
        upper_changeset_id = self.repo.get_changeset_id_from_revision_id(upper_revision_id)
        return self.repo.get_state_lineage_from_changeset_ids(lower_changeset_id, upper_changeset_id)

    def save_browser_binary(self, changeset_id, binary_file):
        binary_file.save(self.get_bin_path_from_id(changeset_id))

    def preferred_binary_representation(self, state_id):
        return self.repo.get_revision_id(state_id)

    @property
    def executable_name(self) -> str:
        return "firefox"

    @property
    def browser_name(self) -> str:
        return "firefox"

    # Downloadable binary snapshots (Firefox nightly)

    @staticmethod
    def update_available_snapshot_online_cache():
        old_data = list(MongoDB.get_stored_binary_availability("firefox"))
        new_data = FirefoxBuild.get_data_available_snapshots_online()

        to_add = []
        if len(old_data) == 0:
            to_add = new_data
        else:
            i = 0
            while i < len(new_data) and old_data[0]["state_id"] != new_data[i]["changeset_id"]:
                to_add.append(new_data[i])
                i += 1
        MongoDB.store_binary_availability_online_cache_firefox(to_add)

    @staticmethod
    def get_data_available_snapshots_online():
        # URL is changed to other channel, also change MongoDB binary availability database! (mongodb.py)
        # For mozilla-central channel: https://hg.mozilla.org/mozilla-central/json-firefoxreleases
        # For mozilla-release channel: https://hg.mozilla.org/releases/mozilla-release/json-firefoxreleases
        json_url = "https://hg.mozilla.org/mozilla-central/json-firefoxreleases"
        req = requests.get(json_url)
        data = req.json()
        return [{'changeset_id': build["node"],
                 'binary_url': "%sfirefox-%s.en-US.linux-x86_64.tar.bz2" % (build["files_url"], build["app_version"]),
                 'binary_online': True,
                 'build_id': build["buildid"]
                 } for build in data["builds"] if "linux64" in build["platform"]]

    def has_available_snapshot_online(self, changeset_id):
        # Firefox makes available all their releases, so when only releases are evaluated, this function returns True
        if self.only_releases:
            return True
        return MongoDB.has_binary_available_online("firefox", changeset_id)

    def download_snapshot(self, state_id: int = None, state: FirefoxRepoState = None):
        if state is None and state_id is None:
            raise AttributeError("At least the state_id or state is required as a parameter")
        if state is not None:
            changeset_id = state.id
        else:
            changeset_id = state_id

        if self.only_releases:
            binary_url = "https://ftp.mozilla.org/pub/firefox/releases/%s.0/linux-x86_64/en-US/firefox-%s.0.tar.bz2" % \
                (state.version, state.version)
        else:
            binary_url = MongoDB.get_binary_url("firefox", changeset_id)
        self.logger.debug(f"Downloading {changeset_id} from '{binary_url}'")
        tar_file_path = "/tmp/%s/archive.tar.bz2" % changeset_id
        if os.path.exists(os.path.dirname(tar_file_path)):
            shutil.rmtree(os.path.dirname(tar_file_path))
        os.makedirs(os.path.dirname(tar_file_path))
        with requests.get(binary_url, stream=True) as req:
            with open(tar_file_path, 'wb') as file:
                shutil.copyfileobj(req.raw, file)
        with tarfile.open(tar_file_path, "r:bz2") as tar_ref:
            tar_ref.extractall(os.path.dirname(tar_file_path))
        bin_path = self.get_potential_bin_path(changeset_id)
        os.makedirs(os.path.dirname(bin_path), exist_ok=True)
        unzipped_folder_path = os.path.join(os.path.dirname(tar_file_path), "firefox")
        util.safe_move_dir(unzipped_folder_path, os.path.dirname(bin_path))
        cli.execute_and_return_status("chmod -R a+x %s" % os.path.dirname(bin_path))
        cli.execute_and_return_status("chmod -R a+w %s" % os.path.dirname(bin_path))
        # Remove temporary files in /tmp/COMMIT_POS
        shutil.rmtree(os.path.dirname(tar_file_path))
        # Add policy.json to prevent updating. (this measure is effective from version 60)
        # https://github.com/mozilla/policy-templates/blob/master/README.md
        # (For earlier versions, the prefs.js file is used)
        distributions_path = os.path.join(os.path.dirname(bin_path), "distribution")
        os.makedirs(distributions_path, exist_ok=True)
        policies_path = os.path.join(distributions_path, "policies.json")
        with open(policies_path, "a") as file:
            file.write('{ "policies": { "DisableAppUpdate": true } }')

    def post_build_step(self, state):
        # Save release revision id
        state.release_revision_id = self.repo.get_revision_id(state.id)

    @staticmethod
    def get_version(bin_path):
        command = "./firefox --version"
        output = cli.execute_and_return_output(command, cwd=os.path.dirname(bin_path))
        match = re.match(r'Mozilla Firefox (?P<version>[0-9]+)\.[0-9]+.*', output)
        if match:
            return match.group("version")
        raise AttributeError(
            "Could not determine version of binary at '%s'. Version output: %s" % (bin_path, output))

    def get_driver_path(self, browser_version):
        driver_version = self.get_driver_version(browser_version)
        driver_path = os.path.join(self.driver_folder_path, driver_version)
        if os.path.exists(driver_path):
            return driver_path
        raise AttributeError("Could not find appropriate driver for Firefox %s" % browser_version)

    def get_driver_version(self, browser_version):
        if browser_version not in self.browser_version_to_driver_version.keys():
            raise AttributeError(
                "Could not determine driver version associated with Firefox version %s" % browser_version)
        return self.browser_version_to_driver_version[browser_version]

    browser_version_to_driver_version = {
        '84': "0.28.0",
        '83': "0.28.0",
        '82': "0.27.0",
        '81': "0.27.0",
        '80': "0.27.0",
        '79': "0.27.0",
        '78': "0.27.0",
        '77': "0.27.0",
        '76': "0.27.0",
        '75': "0.27.0",
        '74': "0.27.0",
        '73': "0.27.0",
        '72': "0.27.0",
        '71': "0.27.0",
        '70': "0.27.0",
        '69': "0.27.0",
        '68': "0.26.0",
        '67': "0.26.0",
        '66': "0.26.0",
        '65': "0.25.0",
        '64': "0.26.0",
        '63': "0.26.0",
        '62': "0.26.0",
        '61': "0.26.0",
        '60': "0.26.0",
        '59': "0.25.0",
        '58': "0.20.1",
        '57': "0.20.1",
        '56': "0.19.1",
        '55': "0.20.1",
        '54': "0.17.0",
        '53': "0.16.1",
        '52': "0.15.0",
        '51': "0.15.0",
        '50': "0.15.0"
    }
