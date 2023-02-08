import os
import csv
import logging
import traceback
from abc import ABC, abstractmethod
from bci.data_storage.mongodb import MongoDB
from bci.config import Config
from bci.params import DatabaseParams
from bci.version_control.version_control import RepoState
from bci.browser_build.browser_build import BrowserBuild, BuildNotAvailableError


class EvaluationFramework(ABC):

    def __init__(self):
        self.logger = logging.getLogger("bci")
        self.should_stop = False

    def evaluate(
            self,
            automation: str,
            browser_build: BrowserBuild,
            state: RepoState,
            browser_config: str,
            mech_id: str,
            requested_mech_groups: list,
            extension_file: str,
            additional_cli_options: list,
            cookie_name=None):
        browser_name = browser_build.browser_name
        evaluated_mech_groups = [mech_group for mech_group in requested_mech_groups if self.has_data(
            automation, browser_name, browser_config, extension_file, additional_cli_options, mech_group, state)]
        required_mech_groups = [mech_group for mech_group in requested_mech_groups if mech_group not in evaluated_mech_groups]
        self.logger.info("Requested evaluation for %i mech groups [%s], of which %i still require evaluation [%s]" % (
            len(requested_mech_groups),
            ", ".join(requested_mech_groups),
            len(required_mech_groups),
            ", ".join(required_mech_groups)))

        # Set states of already evaluated mech groups
        for mech_group in evaluated_mech_groups:
            result = self.get_data(
                automation,
                browser_name,
                browser_config,
                extension_file,
                additional_cli_options,
                mech_group,
                mech_id,
                state,
                cookie_name)
            state.set_evaluation_outcome(result)

        # Return if all requested evaluations were found in the cache
        if len(required_mech_groups) == 0:
            return result

        # Perform all requested evaluations which were not cached already
        build_success = browser_build.build(state)
        if not build_success:
            raise BuildNotAvailableError(browser_name, state)
        bin_path = browser_build.get_bin_path(state)
        browser_version = browser_build.get_version(bin_path)
        if automation == "selenium":
            driver_version = browser_build.get_driver_version(browser_version)
            driver_exec = browser_build.get_driver_path(browser_version)
        else:
            driver_version = None
            driver_exec = None

        for mech_group in required_mech_groups:
            if self.should_stop:
                # Reset should_stop
                self.should_stop = False
                # TODO: should return a specific value indicating the evaluation has been stopped by the user
                return True
            try:
                result = self.perform_specific_evaluation(
                    automation,
                    browser_name,
                    browser_version,
                    driver_version,
                    browser_config,
                    extension_file,
                    additional_cli_options,
                    mech_id,
                    mech_group,
                    bin_path,
                    driver_exec,
                    state,
                    cookie_name)
                state.set_evaluation_outcome(result)
                self.logger.info("Evaluation executed for '%s' (%s)" % (state, mech_group))
            except Exception as e:
                state.set_evaluation_error(str(e))
                self.logger.error("An error occurred during evaluation", exc_info=True)
                traceback.print_exc()
                result = None
        browser_build.remove_bin_folder(state.id)
        return result

    @staticmethod
    def get_data_path(browser, state, config):
        if browser == "chromium":
            data_folder = os.path.join(Config.chromium_data_folder_path, "%s/%s" % (state.id, config))
        elif browser == "firefox":
            data_folder = os.path.join(Config.firefox_data_folder_path, "%s/%s" % (state.id, config))
        else:
            raise AttributeError("Unknown browser '%s'" % browser)
        if not os.path.exists(data_folder):
            os.makedirs(data_folder)
        return data_folder

    @abstractmethod
    def perform_specific_evaluation(
            self,
            automation: str,
            browser: str,
            browser_version: str,
            driver_version: str,
            browser_config: str,
            extension_file: str,
            additional_cli_options: list,
            mech_id: str,
            mech_group: str,
            browser_binary: str,
            driver_exec: str,
            state: RepoState,
            cookie_name: str):
        pass

    @property
    @classmethod
    @abstractmethod
    def db_class(cls) -> MongoDB:
        pass

    @classmethod
    def has_data(
            cls: MongoDB,
            automation: str,
            browser: str,
            config: str,
            extension_name: str,
            additional_cli_options: list,
            mech_group: str,
            state: RepoState):
        return cls.db_class.get_instance().has_data(
            automation, browser, config, extension_name, additional_cli_options, mech_group, state)

    @classmethod
    def get_data(
            cls: MongoDB,
            automation: str,
            browser: str,
            browser_config: str,
            extension_name: str,
            additional_cli_options: list,
            mech_group: str,
            mech_id: str,
            state: RepoState,
            cookie_name: str):
        return cls.db_class.get_instance().get_data(automation, browser, browser_config, extension_name,
                                                    additional_cli_options, mech_group, mech_id, state, cookie_name)

    @classmethod
    def get_data_with_params(cls, params: DatabaseParams):
        return cls.db_class.get_instance().get_data_with_params(params)

    @classmethod
    def has_all_data_with_params(cls, params: DatabaseParams):
        return cls.db_class.get_instance().has_all_data_with_params(params)

    @abstractmethod
    def get_data_in_json(self, data_path, mech_group):
        pass

    @staticmethod
    def get_extension_path(browser: str, extension_file: str):
        folder_path = Config.get_extension_folder_path(browser)
        path = os.path.join(folder_path, extension_file)
        if not os.path.isfile(path):
            raise AttributeError("Could not find file '%s'" % path)
        return path

    def stop_gracefully(self):
        self.should_stop = True

    @abstractmethod
    def get_mech_groups(self, project=None):
        """
        Returns the available mechanism groups for this evaluation framework.
        """

    @staticmethod
    def read_csv_file(file_path) -> dict:
        json_data = {}
        if os.path.isfile(file_path):
            with open(file_path) as csv_file:
                rows = csv.reader(csv_file)
                for i, row in enumerate(rows):
                    if i < 3:
                        continue
                    json_data[row[0]] = row[1]
            return json_data
        raise AttributeError("Could not find file with path '%s'" % file_path)
