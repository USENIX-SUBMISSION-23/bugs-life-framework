import os
import shutil
from bci.evaluations.evaluation_framework import EvaluationFramework
from bci.config import Config
from bci.version_control.version_control import RepoState
from bci.evaluations.custom.custom_mongodb import CustomMongoDB
from bci.evaluations.jar_interface import Jar


class CustomEvaluationFramework(EvaluationFramework):

    db_class = CustomMongoDB

    def __init__(self):
        super().__init__()
        self.tests_per_project = {}
        self.tests = {}
        self.initialize_tests_and_url_queues()

    def initialize_tests_and_url_queues(self):
        used_test_names = {}
        test_folder_path = Config.custom_test_folder
        page_folder_path = Config.custom_page_folder
        if not os.path.isdir(test_folder_path):
            return
        project_names = [name for name in os.listdir(test_folder_path) if os.path.isdir(os.path.join(test_folder_path, name))]
        for project_name in project_names:
            # Find tests in folder
            project_path = os.path.join(test_folder_path, project_name)
            self.tests_per_project[project_name] = {}
            for test_name in os.listdir(project_path):
                if test_name in used_test_names:
                    raise AttributeError(f"Test name '{test_name}' should be unique over all projects (found in {project_name} and {used_test_names[test_name]})")
                used_test_names[test_name] = project_name
                test_path = os.path.join(project_path, test_name)
                if os.path.isdir(test_path):
                    with open(os.path.join(test_path, "url_queue.txt")) as file:
                        self.tests_per_project[project_name][test_name] = file.readlines()
                        self.tests[test_name] = self.tests_per_project[project_name][test_name]
            # Find remaining tests by checking the pages hosting tests
            project_path = os.path.join(page_folder_path, project_name)
            for test_name in os.listdir(project_path):
                test_path = os.path.join(project_path, test_name)
                for domain in os.listdir(test_path):
                    main_folder_path = os.path.join(project_path, test_path, domain, "main")
                    if os.path.exists(main_folder_path) and test_name not in used_test_names:
                        used_test_names[test_name] = project_name
                        self.tests_per_project[project_name][test_name] = [
                            f"https://{domain}/custom/{test_name}/main",
                            "https://adition.com/report/?leak=baseline"
                        ]
                        self.tests[test_name] = self.tests_per_project[project_name][test_name]

    def perform_specific_evaluation(
            self,
            automation: str,
            browser: str,
            browser_version: str,
            driver_version: str,
            browser_config: str,
            extension_name: str,
            additional_cli_options: list,
            mech_id: str,
            mech_group: str,
            browser_binary: str,
            driver_exec: str,
            state: RepoState,
            cookie_name: str):
        if not self.has_data(automation, browser, browser_config, extension_name, additional_cli_options, mech_group, state):
            self.logger.info(f"Starting browser evaluation for {browser} v{browser_version} with driver {driver_exec}")

            tries = 0
            is_dirty = True
            while tries < 3 and is_dirty:
                if tries > 0:
                    self.logger.info(f"Evaluation failed; trying again (try {tries})")
                tries += 1
                data_folder = self.get_data_path(browser, state, browser_config)
                extension_path = self.get_extension_path(browser, extension_name) if extension_name else None
                Jar.do_automation(automation, browser, browser_version, browser_config, extension_path,
                                  browser_binary, additional_cli_options, driver_exec, data_folder, mech_group,
                                  custom=True, url_queue=self.tests[mech_group])
                json_data = self.get_data_in_json(data_folder, mech_group)
                is_dirty = self.is_dirty_evaluation(data_folder)
                # Remove csv files
                try:
                    shutil.rmtree(os.path.dirname(data_folder))
                except OSError:
                    self.logger.error("Could not remove temporary data folder", exc_info=True)

            self.db_class.get_instance().store_data(automation, browser, browser_version, driver_version, browser_config,
                                                    extension_name, additional_cli_options, state, mech_group,
                                                    json_data, is_dirty)

        return self.get_data(automation, browser, browser_config, extension_name,
                             additional_cli_options, mech_group, mech_id, state, cookie_name)

    def has_data(
            self,
            automation: str,
            browser: str,
            config: str,
            extension_name: str,
            additional_cli_options: list,
            mech_group: str,
            state: RepoState):
        return CustomMongoDB.get_instance().has_data(
            automation, browser, config, extension_name, additional_cli_options, mech_group, state)

    def get_data_in_json(self, data_path, _) -> dict:
        data_file_path = os.path.join(data_path, "custom.csv")
        return self.read_csv_file(data_file_path)

    @staticmethod
    def is_dirty_evaluation(data_path):
        """
        Returns True if an exception was thrown during the evaluation, otherwise returns False.
        """
        data_exception_file_path = os.path.join(data_path, "custom_EXCEPTION.csv")
        return os.path.isfile(data_exception_file_path)

    def get_mech_groups(self, project=None):
        if project:
            return sorted(self.tests_per_project[project].keys())
        return sorted(self.tests_per_project.keys())
