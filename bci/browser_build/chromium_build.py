import os
import shutil
import zipfile
import re
import requests
from bci import util
from bci import cli
from bci.browser_build.browser_build import BrowserBuild
from bci.version_control.chromium_vc import ChromiumRepo, ChromiumRepoState, ChromiumRepoLineage
from bci.data_storage.mongodb import MongoDB


class ChromiumBuild(BrowserBuild):

    def __init__(self, repo_path, bin_folder_path, data_folder_path, driver_folder_path):
        super().__init__(repo_path, bin_folder_path, data_folder_path, driver_folder_path)
        self.os_name = "Linux_x64"
        self.os_name_short = "linux"
        self.repo = ChromiumRepo(repo_path)

    def save_browser_binary(self, changeset_id, binary_file):
        binary_file.save(self.get_bin_path_from_id(changeset_id))

    @property
    def executable_name(self) -> str:
        return "chrome"

    @property
    def browser_name(self) -> str:
        return "chromium"

    def get_state_lineage_from_versions(self, lower_version, upper_version):
        full_lower_version = self.get_full_version(lower_version)
        full_upper_version = self.get_full_version(upper_version)
        lower_commit_pos = self.get_first_commit_pos(full_lower_version)
        upper_commit_pos = self.get_first_commit_pos(full_upper_version)
        commit_pos_list = self.get_commit_pos_lineage(lower_commit_pos, upper_commit_pos)
        evaluation_targets = None
        if self.only_releases:
            evaluation_targets = []
            short_lower_version = self.get_short_version(lower_version)
            short_upper_version = self.get_short_version(upper_version)
            for version in range(int(short_lower_version), int(short_upper_version) + 1):
                full_version = self.get_full_version(str(version))
                evaluation_targets.append(self.get_first_commit_pos(full_version))
            self.logger.info(f"Boundaries found: {lower_commit_pos} - {upper_commit_pos} (of which to evaluate {len(evaluation_targets)})")
        else:
            self.logger.info(f"Boundaries found: {lower_commit_pos} - {upper_commit_pos} (of which to evaluate all)")
        return ChromiumRepoLineage(commit_pos_list, evaluation_targets=evaluation_targets)

    def get_state_lineage_from_commit_positions(self, lower_commit_pos, upper_commit_pos):
        commit_pos_list = self.get_commit_pos_lineage(lower_commit_pos, upper_commit_pos)
        self.logger.info(f"Boundaries found: {lower_commit_pos} - {upper_commit_pos} (of which to evaluate all)")
        return ChromiumRepoLineage(commit_pos_list)

    def get_full_version(self, version):
        if re.match(r'[0-9]+\.[0-9]+\.[0-9]+', version):
            return version + ".0"
        if re.match(r'[0-9]{2}', version):
            return self.full_versions[version] + ".0"
        raise AttributeError("Could not convert version '%i' to full version" % version)

    @staticmethod
    def get_short_version(version):
        if re.match(r'^[0-9]+$', version):
            return version
        if re.match(r'^[0-9]+(\.[0-9]+)+$', version):
            return version.split(".")[0]
        raise AttributeError("Could not convert version '%i' to short version" % version)

    # Downloadable binary snapshots

    def has_available_snapshot_online(self, commit_pos):
        cached_binary_available_online = MongoDB.has_binary_available_online("chromium", commit_pos)
        if cached_binary_available_online is not None:
            return cached_binary_available_online
        url = "https://www.googleapis.com/storage/v1/b/chromium-browser-snapshots/o/%s%%2F%s%%2Fchrome-%s.zip"\
            % (self.os_name, commit_pos, self.os_name_short)
        req = requests.get(url)
        has_binary_online = req.status_code == 200
        MongoDB.store_binary_availability_online_cache("chromium", commit_pos, has_binary_online)
        return has_binary_online

    def download_snapshot(self, state_id: int = None, state: ChromiumRepoState = None):
        if state is None and state_id is None:
            raise AttributeError("At least the state_id or state is required as a parameter")
        if state is not None:
            commit_pos = state.id
        else:
            commit_pos = state_id

        if self.has_available_snapshot_locally(commit_pos):
            self.logger.debug("%s was already downloaded (%s)" % (commit_pos, self.get_bin_path_from_id(commit_pos)))
            return
        url = \
            "https://www.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/%s%%2F%s%%2Fchrome-%s.zip?alt=media"\
            % (self.os_name, commit_pos, self.os_name_short)
        self.logger.info(f"Downloading {commit_pos} from '{url}'")
        zip_file_path = "/tmp/%s/archive.zip" % commit_pos
        if os.path.exists(os.path.dirname(zip_file_path)):
            shutil.rmtree(os.path.dirname(zip_file_path))
        os.makedirs(os.path.dirname(zip_file_path))
        with requests.get(url, stream=True) as req:
            with open(zip_file_path, 'wb') as file:
                shutil.copyfileobj(req.raw, file)
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(os.path.dirname(zip_file_path))
        bin_path = self.get_potential_bin_path(commit_pos)
        os.makedirs(os.path.dirname(bin_path), exist_ok=True)
        unzipped_folder_path = os.path.join(os.path.dirname(zip_file_path), "chrome-linux")
        util.safe_move_dir(unzipped_folder_path, os.path.dirname(bin_path))
        cli.execute_and_return_status("chmod -R a+x %s" % os.path.dirname(bin_path))
        # Remove temporary files in /tmp/COMMIT_POS
        shutil.rmtree(os.path.dirname(zip_file_path))

    def post_build_step(self, state):
        pass

    @staticmethod
    def get_commit_pos_lineage(ancestor_commit_pos, descendant_commit_pos):
        commit_pos_lineage = []
        for commit_pos in range(int(ancestor_commit_pos), int(descendant_commit_pos) + 1):
            # if self.has_available_snapshot_online(commit_pos):
            #    commit_pos_lineage.append(commit_pos)
            commit_pos_lineage.append(str(commit_pos))
        return commit_pos_lineage

    @staticmethod
    def get_first_commit_pos(version):
        # This version does not have a commit position available online
        if version == "57.0.2987.0":
            # This is just an estimation
            return "444943"
        if version in ChromiumBuild.branch_base_positions:
            return ChromiumBuild.branch_base_positions[version]
        url = "https://omahaproxy.appspot.com/deps.json?version=%s" % version
        req = requests.get(url)
        if req.ok:
            data = req.json()
            return data["chromium_base_position"]
        raise AttributeError("Could not find first commit_pos for '%s' at '%s'" % (version, url))

    @staticmethod
    def get_version(bin_path):
        command = "./chrome --version"
        output = cli.execute_and_return_output(command, cwd=os.path.dirname(bin_path))
        match = re.match(r'Chromium (?P<version>[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)', output)
        if match:
            return match.group("version")
        raise AttributeError("Could not determine version of binary at '%s'. Version output: %s" % (bin_path, output))

    def get_driver_path(self, full_browser_version):
        driver_version = self.get_driver_version(full_browser_version)
        driver_path = os.path.join(self.driver_folder_path, driver_version)
        if os.path.exists(driver_path):
            return driver_path
        raise AttributeError("Could not find appropriate driver for Chromium %s" % full_browser_version)

    def get_driver_version(self, browser_version):
        short_browser_version = browser_version.split('.')[0]
        if short_browser_version not in self.browser_version_to_driver_version.keys():
            raise AttributeError("Could not determine driver version associated with Chromium version %s" % browser_version)
        return self.browser_version_to_driver_version[short_browser_version]

    full_versions = {
        '100': "100.0.4896",
        '99': "99.0.4844",
        '98': "98.0.4758",
        '97': "97.0.4692",
        '96': "96.0.4664",
        '95': "95.0.4638",
        '94': "94.0.4606",
        '93': "93.0.4577",
        '92': "92.0.4515",
        '91': "91.0.4472",
        '90': "90.0.4430",
        '89': "89.0.4389",
        '88': "88.0.4324",
        '87': "87.0.4280",
        '86': "86.0.4240",
        '85': "85.0.4183",
        '84': "84.0.4147",
        '83': "83.0.4103",
        '82': "81.0.4044",
        '81': "81.0.4044",
        '80': "80.0.3987",
        '79': "79.0.3945",
        '78': "78.0.3904",
        '77': "77.0.3865",
        '76': "76.0.3809",
        '75': "75.0.3770",
        '74': "74.0.3729",
        '73': "73.0.3683",
        '72': "72.0.3626",
        '71': "71.0.3578",
        '70': "70.0.3538",
        '69': "69.0.3497",
        '68': "68.0.3440",
        '67': "67.0.3396",
        '66': "66.0.3359",
        '65': "65.0.3325",
        '64': "64.0.3282",
        '63': "63.0.3239",
        '62': "62.0.3202",
        '61': "61.0.3163",
        '60': "60.0.3112",
        '59': "59.0.3071",
        '58': "58.0.3029",
        '57': "57.0.2987",
        '56': "56.0.2924",
        '55': "55.0.2883",
        '54': "54.0.2840",
        '53': "53.0.2785",
        '52': "52.0.2743",
        '51': "51.0.2704",
        '50': "50.0.2661",
        '49': "49.0.2623",
        '48': "48.0.2564",
        '47': "47.0.2526",
        '46': "46.0.2490",
        '45': "45.0.2454",
        '44': "44.0.2403",
        '43': "43.0.2357",
        '42': "42.0.2311",
        '41': "41.0.2272",
        '40': "40.0.2214",
        '39': "39.0.2171",
        '38': "38.0.2125",
        '37': "37.0.2062",
        '36': "36.0.1985",
        '35': "35.0.1916",
        '34': "34.0.1847",
        '33': "33.0.1750",
        '32': "32.0.1700",
        '31': "31.0.1650",
        '30': "30.0.1599",
        '29': "29.0.1547",
        '28': "28.0.1500",
        '27': "27.0.1453",
        '26': "26.0.1410",
        '25': "25.0.1364",
        '24': "24.0.1312",
        '23': "23.0.1271",
        '22': "22.0.1229",
        '21': "21.0.1180",
        '20': "20.0.1132",
        '19': "19.0.1084",
        '18': "18.0.1025",
        '17': "17.0.963",
        '16': "16.0.912",
        '15': "15.0.874",
        '14': "14.0.835",
        '13': "13.0.782",
        '12': "12.0.742",
        '11': "11.0.696",
        '10': "10.0.648"
    }

    # Branch base positions cannot be infered fron omahaproxy for older Chromium versions.
    branch_base_positions = {
        '42.0.2311.0': "317474",
        '41.0.2272.0': "310958",
        '40.0.2214.0': "303346",
        '39.0.2171.0': "297060",
        '38.0.2125.0': "290040",
        '37.0.2062.0': "278856",
        '36.0.1985.0': "269467",
        '35.0.1916.0': "260298",
        '34.0.1847.0': "251904",
        '33.0.1750.0': "241107",
        '32.0.1700.0': "232870",
        '31.0.1650.0': "224845",
        '30.0.1599.0': "217147",
        '29.0.1547.0': "208345",
        '28.0.1500.0': "198577",
        '27.0.1453.0': "190564",
        '26.0.1410.0': "181864",
        '25.0.1364.0': "173683",
        '24.0.1312.0': "164863",
        '23.0.1271.0': "157509",
        '22.0.1229.0': "150285",
        '21.0.1180.0': "142910",
        '20.0.1132.0': "135598",
        '19.0.1084.0': "129376",
        '18.0.1025.0': "119867",
        '17.0.963.0': "113143",
        '16.0.912.0': "106036",
        '15.0.874.0': "99889",
        '14.0.835.0': "94025",
        '13.0.782.0': "87433",
        '12.0.742.0': "82248",
        '11.0.696.0': "77261",
        '10.0.648.0': "72316"
    }

    browser_version_to_driver_version = {
        '88': "88.0.4324.96",
        '87': "87.0.4280.88",
        '86': "86.0.4240.22",
        '85': "85.0.4183.87",
        '84': "84.0.4147.30",
        '83': "83.0.4103.39",
        '82': "81.0.4044.69",  # No chromium driver released for 82
        '81': "81.0.4044.69",
        '80': "80.0.3987.16",  # 80.0.3987.16 80.0.3987.106
        '79': "79.0.3945.36",
        '78': "78.0.3904.11",
        '77': "77.0.3865.40",
        '76': "76.0.3809.126",
        '75': "75.0.3770.8",
        '74': "74.0.3729.6",
        '73': "73.0.3683.68",
        '72': "72.0.3626.7",
        '71': "71.0.3578.80",
        '70': "70.0.3538.97",
        '69': "2.42.591071",
        '68': "2.41.578700",
        '67': "2.40.565383",
        '66': "2.38.552522",
        '65': "2.37.544315",
        '64': "2.36.540471",
        '63': "2.35.528139",
        '62': "2.34.522913",
        '61': "2.33.506092",
        '60': "2.32.498513",
        '59': "2.31.488763",  # From here on not working
        '58': "2.29.461571",
        '57': "2.29.461571",
        '56': "2.29.461571",
        '55': "2.27.440175",
        '54': "2.23.409687",
        '53': "2.23.409687",  # Based on Selenoid https://aerokube.com/images/latest/
        '52': "2.23.409687",  # Based on Selenoid
        '51': "2.22.397932",  # Tried also with 2.21 and 2.23, to no avail
        '50': "2.22.397932",  # Based on Selenoid
        '49': "2.21.371461",  # Based on Selenoid
        '48': "2.21.371461",
        '47': "2.21.371461",
        '46': "2.20.353124",
        '45': "2.20.353124",
        '44': "2.19.346067",
        '43': "2.19.346067",
        '42': "2.18.343837",
        '41': "2.18.343837",
        '40': "2.18.343837",
    }
