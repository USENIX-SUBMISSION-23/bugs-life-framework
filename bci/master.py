import traceback
import logging
from bci.browser_build.browser_build import BrowserBuild
from bci.config import Config
from bci.params import DatabaseParams, EvalParams
from bci.data_storage.mongodb import MongoDB, ServerException
from bci.browser_build.firefox_build import FirefoxBuild
from bci.browser_build.chromium_build import ChromiumBuild
from bci.search_strategy.sequence_strategy import SequenceStrategy
from bci.version_control.version_control import RepoLineage, RepoState
from bci.search_strategy.n_ary_search import NArySearch
from bci.search_strategy.n_ary_sequence import NArySequence, SequenceFinished
from bci.search_strategy.composite_search import CompositeSearch
from bci.evaluations.samesite.samesite_evaluation import SameSiteEvaluationFramework
from bci.evaluations.custom.custom_evaluation import CustomEvaluationFramework
from bci.evaluations.xsleaks.evaluation import XSLeaksEvaluation
from bci.distribution.manager import ContainerManager

logger = None
stop = False

evaluations = []
evaluation_framework = None
container_manager = None
available_evaluation_frameworks = {}

firefox_build = None
chromium_build = None


def initialize():
    global logger
    global firefox_build
    global chromium_build

    Config.load_config()
    Config.configure_loggers()

    logger = logging.getLogger("bci")

    try:
        MongoDB.connect()
    except ServerException:
        logger.critical("A database server occurred", exc_info=True)
        return

    inititialize_available_evaluation_frameworks()

    firefox_build = FirefoxBuild(
        Config.firefox_repo_path,
        Config.firefox_bin_folder_path,
        Config.firefox_data_folder_path,
        Config.firefox_driver_folder_path
    )
    chromium_build = ChromiumBuild(
        Config.chromium_repo_path,
        Config.chromium_bin_folder_path,
        Config.chromium_data_folder_path,
        Config.chromium_driver_folder_path
    )

    logger.info("Master initialized")


def run(eval_params: EvalParams):
    global stop
    global evaluation_framework
    global container_manager

    logger.info(
        "Starting evaluation for %s (%s)"
        % (eval_params.browser, ", ".join(eval_params.mech_groups))
    )
    stop = False
    evaluation_framework = get_specific_evaluation_framework(
        eval_params.evaluation_framework_name
    )
    container_manager = ContainerManager(eval_params.nb_of_containers)

    try:
        browser_build = get_browser_build(eval_params.browser)
        browser_build.set_only_releases(eval_params.only_release_commits)
        state_lineage = get_state_lineage(
            eval_params.browser,
            eval_params.lower_version,
            eval_params.upper_version,
            eval_params.lower_state_id,
            eval_params.upper_state_id,
            only_release_commits=eval_params.only_release_commits,
        )

        search_strategy = parse_search_strategy(
            eval_params.search_strategy, state_lineage, browser_build, eval_params.nb_of_containers, eval_params.sequence_limit
        )

        # The state_lineage is put into self.evaluation as a means to check on the process through front-end
        evaluations.append(state_lineage)

        try:
            current_state = search_strategy.next()
            while stop is False:
                database_params = eval_params.get_database_params(current_state.id)

                # Callback function for sequence strategy
                update_outcome = get_update_outcome_cb(search_strategy, database_params, current_state)

                # Check whether state is already evaluated
                if evaluation_framework.has_all_data_with_params(database_params):
                    logger.info(f"State '{current_state.id}' already evaluated.")
                    update_outcome()
                    current_state = search_strategy.next()
                    continue

                # Start worker to perform evaluation
                worker_params = eval_params.get_worker_params(current_state.id)
                container_manager.start_container(worker_params, update_outcome)
                logger.info(f"Container started for {current_state}")

                current_state = search_strategy.next()
        except SequenceFinished:
            logger.debug("Last evaluation has started")

    except Exception as e:
        logger.critical("A critical error occurred", exc_info=True)
        raise e

    # Gracefully exit
    logger.info("Gracefully stopping evaluation iteration...")
    if stop:
        logger.info("Reason of stopping: user end signal")
        stop = False
    else:
        logger.info("Reason of stopping: last state evaluation started")
    # MongoDB.disconnect()
    logger.info("Waiting for remaining containers to finish")
    container_manager.wait_until_all_containers_are_done()
    logger.info("Ended gracefully, all containers have finished")


def get_update_outcome_cb(search_strategy: SequenceStrategy, params: DatabaseParams, state: RepoState) -> None:
    def cb():
        if params.mech_id is not None:
            outcome = evaluation_framework.get_data_with_params(params)
            search_strategy.update_outcome(state, outcome)
    return cb


def get_state_lineage(
    browser,
    lower_version,
    upper_version,
    lower_state_id,
    upper_state_id,
    only_release_commits,
):
    browser_build = get_browser_build(browser)
    browser_build.set_only_releases(only_release_commits)
    if lower_version is not None and upper_version is not None:
        logger.info(
            "Searching commit boundaries for %s %s to %s"
            % (browser, lower_version, upper_version)
        )
        state_lineage = browser_build.get_state_lineage_from_versions(
            lower_version, upper_version
        )
    elif lower_state_id is not None and upper_state_id is not None:
        state_lineage = browser_build.get_state_lineage_from_commit_positions(
            lower_state_id, upper_state_id
        )
    else:
        raise AttributeError("No upper and lower version/states given")
    logger.info(
        "Found state boundaries: %s and %s (n = %i)"
        % (
            state_lineage.ancestor_state.id,
            state_lineage.descendant_state.id,
            state_lineage.length,
        )
    )
    return state_lineage


def inititialize_available_evaluation_frameworks():
    available_evaluation_frameworks["samesite"] = SameSiteEvaluationFramework()
    available_evaluation_frameworks["custom"] = CustomEvaluationFramework()
    available_evaluation_frameworks["xsleaks"] = XSLeaksEvaluation()


def get_mech_groups_of_evaluation_framework(evaluation_name: str, project=None):
    return get_specific_evaluation_framework(evaluation_name).get_mech_groups(project=project)


def get_specific_evaluation_framework(evaluation_name: str):
    if evaluation_name not in available_evaluation_frameworks.keys():
        raise AttributeError("Could not find a framework for '%s'" % evaluation_name)
    return available_evaluation_frameworks[evaluation_name]


def parse_search_strategy(search_strategy_option: str, state_lineage: RepoLineage, browser_build: BrowserBuild, n: int, sequence_limit: int):
    if search_strategy_option == "bin_seq":
        return NArySequence(state_lineage.states, lambda state: browser_build.is_available_locally_or_online(state.id), n, limit=sequence_limit)
    if search_strategy_option == "bin_search":
        return NArySearch(state_lineage.states, lambda state: browser_build.is_available_locally_or_online(state.id), n)
    if search_strategy_option == "comp_search":
        return CompositeSearch(state_lineage.states, lambda state: browser_build.is_available_locally_or_online(state.id), n, sequence_limit, NArySequence, NArySearch)
    raise AttributeError("Unknown search strategy option '%s'" % search_strategy_option)


def save_browser_binary(browser, state_id, binary_file):
    get_browser_build(browser).save_browser_binary(state_id, binary_file)


def get_browser_build(browser) -> BrowserBuild:
    if browser == "firefox":
        return firefox_build
    if browser == "chromium":
        return chromium_build
    raise AttributeError("Unknown browser '%s'" % browser)


def list_downloaded_binaries(browser):
    return get_browser_build(browser).list_downloaded_binaries()


def list_artisanal_binaries(browser):
    return get_browser_build(browser).list_artisanal_binaries()


def update_artisanal_binaries(browser):
    return get_browser_build(browser).update_artisanal_binaries_meta_data()


def download_online_binary(browser, state_id):
    try:
        logger.info("Download process started")
        get_browser_build(browser).download_snapshot(state_id=state_id)
        logger.info("Download process ended")
    except Exception as e:
        logger.error(str(e))
        traceback.print_exc()


def stop_after_current_evaluation():
    global stop

    logger.info("Received stop signal from user")
    stop = True
    evaluation_framework.stop_gracefully()
