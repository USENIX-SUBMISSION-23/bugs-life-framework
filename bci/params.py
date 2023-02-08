import logging
import bci.browser_cli_options.chromium as cli_options_chromium
import bci.browser_cli_options.firefox as cli_options_firefox


class EvalParams:
    def __init__(self, browser: str, evaluation_framework_name: str, form_data=None) -> None:
        self.logger = logging.getLogger("bci")
        self.browser = browser
        self.evaluation_framework_name = evaluation_framework_name
        self.browser_name = None
        self.configuration_option = None
        self.mech_id = None
        self.mech_groups = []
        self.cookie_name = None
        self.extension_name = None
        self.additional_cli_arguments = []
        self.lower_version = None
        self.upper_version = None
        self.lower_state_id = None
        self.upper_state_id = None
        self.only_release_commits = False
        self.search_strategy = None
        self.automation = None
        self.nb_of_containers = None
        self.sequence_limit = None

        if form_data:
            self.initiliaze_with_form_data(form_data)

    def set_browser_name(self, name: str):
        self.browser_name = name

    def set_configuration_option(self, option: str):
        if option not in ["default", "btpc", "tp", "no-tp", "pb", "allow-java-applets"]:
            raise AttributeError(
                f"Browser configuration option '{option}' is not supported"
            )
        self.configuration_option = option

    def set_mech_id(self, mech_id: str):
        self.mech_id = mech_id

    def set_mech_groups(self, mech_groups: list):
        self.mech_groups = mech_groups

    def set_cookie_name(self, cookie_name: str):
        self.cookie_name = cookie_name

    def set_extension_name(self, name: str):
        self.extension_name = name

    def add_additional_cli_argument(self, argument: str):
        self.additional_cli_arguments.extend(argument)

    def set_lower_version(self, version: str):
        self.lower_version = version

    def set_upper_version(self, version: str):
        self.upper_version = version

    def set_lower_state_id(self, state_id: str):
        self.lower_state_id = state_id

    def set_upper_state_id(self, state_id: str):
        self.upper_state_id = state_id

    def set_only_release_commits(self):
        self.only_release_commits = True

    def set_search_strategy(self, strategy: str):
        self.search_strategy = strategy

    def set_automation(self, automation: str):
        self.automation = automation

    def set_nb_of_containers(self, nb: int):
        self.nb_of_containers = nb

    def set_sequence_limit(self, nb: int):
        self.sequence_limit = nb

    def initiliaze_with_form_data(self, form_data):
        if form_data["lower_version"] != "":
            self.set_lower_version(form_data["lower_version"])
        if form_data["upper_version"] != "":
            self.set_upper_version(form_data["upper_version"])
        if form_data["lower_state_id"] != "":
            self.set_lower_state_id(form_data["lower_state_id"])
        if form_data["upper_state_id"] != "":
            self.set_upper_state_id(form_data["upper_state_id"])

        if "only_release_commits" in form_data:
            self.set_only_release_commits()

        self.set_automation(form_data["automation_option"])

        self.set_search_strategy(form_data["search_strategy_option"])

        self.set_nb_of_containers(int(form_data["nb_of_containers"]))
        self.set_sequence_limit(int(form_data["sequence_limit"]))

        if "btpc" in form_data:
            self.set_configuration_option("btpc")
        elif "tp" in form_data:
            self.set_configuration_option("tp")
        elif "no-tp" in form_data:
            self.set_configuration_option("no-tp")
        elif "pb" in form_data:
            self.set_configuration_option("pb")
        elif "allow-java-applets" in form_data:
            self.set_configuration_option("allow-java-applets")
        else:
            self.set_configuration_option("default")

        if "extension" in form_data:
            self.set_extension_name(form_data["extension"])

        for potential_cli_option in self.get_available_cli_options(self.browser):
            if potential_cli_option in form_data:
                self.add_additional_cli_argument(
                    self.get_associated_cli_argument(self.browser, potential_cli_option)
                )

        if form_data["mech_id"] != "":
            self.set_mech_id(form_data["mech_id"])

        selected_mech_group_tags = list(
            filter(
                lambda x: x.startswith("mg_") and form_data[x] == "true",
                form_data.keys(),
            )
        )
        if len(selected_mech_group_tags) == 0:
            all_mech_group_tags = list(
                filter(
                    lambda x: x.startswith("mg_") and form_data[x] == "true",
                    form_data.keys(),
                )
            )
            mech_groups = [
                mech_group_tag.replace("mg_", "")
                for mech_group_tag in all_mech_group_tags
            ]
        else:
            mech_groups = [
                mech_group_tag.replace("mg_", "")
                for mech_group_tag in selected_mech_group_tags
            ]
        self.set_mech_groups(mech_groups)

        leak = form_data["leak"]
        if leak == "request":
            self.set_cookie_name(None)
        else:
            if "cookie_name" in form_data:
                self.set_cookie_name(form_data["cookie_name"])
            else:
                self.set_cookie_name("generic")

    @staticmethod
    def get_available_cli_options(browser: str):
        if browser == "chromium":
            return cli_options_chromium.get_all_cli_options()
        if browser == "firefox":
            return cli_options_firefox.get_all_cli_options()
        raise AttributeError("Unknown browser '%s'" % browser)

    @staticmethod
    def get_associated_cli_argument(browser: str, cli_option: str) -> list:
        if browser == "chromium":
            return cli_options_chromium.get_associated_arguments(cli_option)
        if browser == "firefox":
            return cli_options_firefox.get_associated_arguments(cli_option)
        raise AttributeError("Unknown browser '%s'" % browser)

    def check_consistency(self):
        if not self.automation:
            self.logger.error("A browser automation should be selected")
            return False
        return True

    def get_worker_params(self, state_id: str):
        return WorkerParams(state_id, self)

    def get_database_params(self, state_id: str):
        return DatabaseParams(state_id, self)


class WorkerParams:

    def __init__(self, state_id: str, eval_params: EvalParams) -> None:
        self.evaluation_framework_name = eval_params.evaluation_framework_name
        self.automation = eval_params.automation
        self.browser = eval_params.browser
        self.state_id = state_id
        self.configuration_option = eval_params.configuration_option
        self.mech_id = eval_params.mech_id
        self.mech_groups = eval_params.mech_groups
        self.extension_name = eval_params.extension_name
        self.additional_cli_options = eval_params.additional_cli_arguments
        self.cookie_name = eval_params.cookie_name


class DatabaseParams:

    def __init__(self, state_id: str, eval_params: EvalParams) -> None:
        self.automation = eval_params.automation
        self.browser_name = eval_params.browser
        self.browser_setting = eval_params.configuration_option
        self.extension_name = eval_params.extension_name
        self.additional_cli_options = eval_params.additional_cli_arguments
        self.mech_groups = eval_params.mech_groups
        self.mech_id = eval_params.mech_id
        self.state_id = int(state_id) if state_id.isdigit() else state_id
        self.cookie_name = eval_params.cookie_name

    def to_mongodb_query(self):
        query = {
            "state_id": self.state_id,
            "browser_automation": self.automation,
            "browser_config": self.browser_setting,
            "mech_group": {"$in": self.mech_groups},
            "extension_name": self.extension_name,
        }
        if len(self.additional_cli_options) > 0:
            query["additional_cli_options"] = {"$size": len(self.additional_cli_options), "$all": self.additional_cli_options}
        return query
