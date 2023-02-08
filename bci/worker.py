import click
from bci.browser_build.browser_build import BrowserBuild
from bci.config import Config
from bci.data_storage.mongodb import MongoDB
from bci.version_control.firefox_vc import FirefoxRepoState
from bci.version_control.chromium_vc import ChromiumRepoState
from bci.browser_build.firefox_build import FirefoxBuild
from bci.browser_build.chromium_build import ChromiumBuild
from bci.evaluations.samesite.samesite_evaluation import SameSiteEvaluationFramework
from bci.evaluations.custom.custom_evaluation import CustomEvaluationFramework
from bci.evaluations.xsleaks.evaluation import XSLeaksEvaluation

logger = None


@click.command()
@click.option("--framework-name", "-f")
@click.option("--automation", "-a")
@click.option("--browser", "-b")
@click.option("--state_id", "-s")
@click.option("--config", "-c")
@click.option("--mech_id", "-i")
@click.option("--mech_groups", "-g", multiple=True)
@click.option("--extension_file", "-e")
@click.option("--browser_cli_options", "-o", multiple=True, default=[])
@click.option("--cookie_name", "-n")
def run(
    framework_name,
    automation,
    browser,
    state_id,
    config,
    mech_id,
    mech_groups,
    extension_file,
    browser_cli_options,
    cookie_name,
):
    Config.load_config()
    Config.configure_loggers()
    MongoDB.connect()

    # click passes options with multiple=True as a tuple, so we convert it to a list
    browser_cli_options = list(browser_cli_options)
    evaluation_framework = get_evaluation_framework(framework_name)
    browser_build, repo_state = get_browser_build_and_repo_state(browser, state_id)

    evaluation_framework.evaluate(
        automation,
        browser_build,
        repo_state,
        config,
        mech_id,
        mech_groups,
        extension_file,
        browser_cli_options,
        cookie_name=cookie_name,
    )


# automation_option, browser_build,
# closest_to_ancestor_state, config, mech_id,
# mech_groups, extension_file,
# additional_cli_options, cookie_name=cookie_name


def get_evaluation_framework(framework_name):
    if framework_name == "samesite":
        return SameSiteEvaluationFramework()
    elif framework_name == "custom":
        return CustomEvaluationFramework()
    elif framework_name == "xsleaks":
        return XSLeaksEvaluation()
    else:
        raise AttributeError(f"Unknown framework name '{framework_name}'")


def get_browser_build_and_repo_state(browser: str, state_id: str) -> BrowserBuild:
    if browser == "firefox":
        return FirefoxBuild(
            Config.firefox_repo_path,
            Config.firefox_bin_folder_path,
            Config.firefox_data_folder_path,
            Config.firefox_driver_folder_path,
        ), FirefoxRepoState(state_id)

    elif browser == "chromium":
        return ChromiumBuild(
            Config.chromium_repo_path,
            Config.chromium_bin_folder_path,
            Config.chromium_data_folder_path,
            Config.chromium_driver_folder_path,
        ), ChromiumRepoState(state_id)
    else:
        raise AttributeError(f"Unknown browser '{browser}'")


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    run()
