import os
import logging
import logging.handlers
import threading
from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO
from bci import master
from bci.web_front.log_printer import LogPrinter
from bci.config import Config
from bci.params import EvalParams
import bci.browser_cli_options.chromium as cli_options_chromium
import bci.browser_cli_options.firefox as cli_options_firefox

# pylint: disable=global-statement
THREAD = None

app = Flask(__name__)
socketio = SocketIO(app)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["post"])
def run_post():
    args = request.form
    if (
        "browser" not in args
        or "lower_version" not in args
        or "upper_version" not in args
        or "mech_id" not in args
    ):
        return error_redirect("Not all parameters were set")
    browser = args["browser"]
    lower_version = args["lower_version"]
    upper_version = args["upper_version"]
    mech_id = args["mech_id"]

    if browser == "" or lower_version == "" or upper_version == "" or mech_id == "":
        return error_redirect("Not all parameters were set")

    global THREAD
    if THREAD is not None:
        return "Another thread is already active."

    THREAD = threading.Thread(
        target=master.run,
        args=(browser, lower_version, upper_version, mech_id, log_printer),
    )

    return redirect(url_for("run_get"))


@app.route("/run", methods=["get"])
def run_get():
    return render_template("run.html")


@app.route("/binaries/file_upload/<string:browser>/<string:state_id>", methods=["post"])
def upload_binary(browser, state_id):
    file = request.files["file"]
    master.save_browser_binary(browser, state_id, file)
    return "file uploaded successfully"


@app.route("/binaries/<string:browser>", methods=["get"])
def binaries(browser):
    downloaded_binaries = master.list_downloaded_binaries(browser)
    artisanal_binaries = master.list_artisanal_binaries(browser)
    return render_template(
        "binaries/overview.html",
        browser_name=browser,
        downloaded_binaries=downloaded_binaries,
        artisanal_binaries=artisanal_binaries,
    )


@app.route("/binaries/<string:browser>", methods=["post"])
def download_binary(browser):
    global THREAD
    if THREAD is not None and THREAD.is_alive():
        logging.getLogger("web_gui").error("Another thread is still busy")
        return "Another thread is still busy"

    state_id = request.form["snapshot_id"]
    THREAD = threading.Thread(
        target=master.download_online_binary, args=(browser, state_id)
    )
    THREAD.start()
    return "200"


@app.route("/binaries/<string:browser>/update", methods=["post"])
def update_artisanal_meta_data(browser):
    global THREAD
    if THREAD is not None and THREAD.is_alive():
        logging.getLogger("web_gui").error("Another thread is still busy")
        return "Another thread is still busy"

    THREAD = threading.Thread(
        target=master.update_artisanal_binaries, args=(browser,)
    )
    THREAD.start()
    return "Updating started"


@app.route("/evaluations/<string:browser>", methods=["get"])
def evaluations(browser):
    extensions = get_available_extensions(browser)
    cli_options = get_available_cli_options(browser)
    mech_groups = master.get_mech_groups_of_evaluation_framework("samesite")
    return render_template(
        "evaluations/overview.html",
        callback="start_evaluation",
        browser_name=browser,
        mech_groups=mech_groups,
        logs=log_printer.logs,
        extensions=extensions,
        cli_options=cli_options,
    )


@app.route("/evaluations/<string:browser>", methods=["post"])
def start_evaluation(browser):
    return generic_state_evaluation("samesite", browser)


def generic_state_evaluation(evaluation_framework_name: str, browser: str):
    global THREAD
    if THREAD is not None and THREAD.is_alive():
        logging.getLogger("web_gui").error("Another thread is still busy")
        return "200"

    params = EvalParams(
        browser, evaluation_framework_name, form_data=request.form
    )

    THREAD = threading.Thread(target=master.run, args=[params])
    THREAD.start()
    return "200"


@app.route("/evaluations/stop", methods=["post"])
def stop_evaluation():
    master.stop_after_current_evaluation()
    return "200"


@app.route("/evaluations/<int:evaluation_id>", methods=["get"])
def evaluation_info(evaluation_id):
    if evaluation_id >= len(master.evaluations):
        return "Evaluation id '%s' does not exist" % evaluation_id
    lineage = master.evaluations[evaluation_id]
    return render_template(
        "evaluations/details.html", evaluation_id=evaluation_id, lineage=lineage
    )


# Private browsing mode evaluation


@app.route("/pb_evaluation/<string:browser>", methods=["get"])
def pb_evaluation_input(browser):
    mech_groups = master.get_mech_groups_of_evaluation_framework(
        "privatebrowsing"
    )
    return render_template(
        "pb_evaluation/input.html",
        browser_name=browser,
        mech_groups=mech_groups,
        logs=log_printer.logs,
    )


@app.route("/pb_evaluation/<string:browser>", methods=["post"])
def start_pb_evaluation(browser):
    global THREAD
    if THREAD is not None and THREAD.is_alive():
        logging.getLogger("web_gui").error("Another thread is still busy")
        return "200"

    lower_version = (
        request.form["lower_version"] if request.form["lower_version"] != "" else None
    )
    upper_version = (
        request.form["upper_version"] if request.form["upper_version"] != "" else None
    )
    lower_state_id = (
        request.form["lower_state_id"] if request.form["lower_state_id"] != "" else None
    )
    upper_state_id = (
        request.form["upper_state_id"] if request.form["upper_state_id"] != "" else None
    )

    only_release_commits = "only_release_commits" in request.form

    browser_automation_option = request.form["automation_option"]

    mech_id = request.form["mech_id"]
    available_mech_groups = master.get_mech_groups_of_evaluation_framework(
        "privatebrowsing"
    )
    mech_groups = []
    for potential_mech_group in available_mech_groups:
        if (
            potential_mech_group in request.form
            and request.form[potential_mech_group] == "true"
        ):
            mech_groups.append(potential_mech_group)
    if len(mech_groups) == 0:
        mech_groups = available_mech_groups

    if "extension" in request.form:
        extension_file = request.form["extension"]
    else:
        extension_file = None

    additional_cli_options = []
    for potential_cli_option in get_available_cli_options(browser):
        if potential_cli_option in request.form:
            additional_cli_options.extend(
                get_associated_cli_argument(browser, potential_cli_option)
            )

    THREAD = threading.Thread(
        target=master.run,
        args=(
            "privatebrowsing",
            browser,
            "pb",
            mech_id,
            mech_groups,
            None,
            extension_file,
            additional_cli_options,
        ),
        kwargs={
            "lower_version": lower_version,
            "upper_version": upper_version,
            "lower_state_id": lower_state_id,
            "upper_state_id": upper_state_id,
            "only_release_commits": only_release_commits,
            "automation_option": browser_automation_option,
        },
    )
    THREAD.start()
    return "200"


# XSLeaks evaluation


@app.route("/xsleaks/<string:browser>", methods=["get"])
def xsleaks_evaluation_input(browser):
    mech_groups = master.get_mech_groups_of_evaluation_framework("xsleaks")
    return render_template(
        "evaluations/overview.html",
        callback="xsleaks_start_evaluation",
        browser_name=browser,
        mech_groups=mech_groups,
        logs=log_printer.logs,
    )


@app.route("/xsleaks/<string:browser>", methods=["post"])
def xsleaks_start_evaluation(browser):
    return generic_state_evaluation("xsleaks", browser)


# Custom tests


@app.route("/eval/custom/<string:project>/<string:browser>", methods=["get"])
def custom_evaluations(browser, project):
    extensions = get_available_extensions(browser)
    cli_options = get_available_cli_options(browser)
    mech_groups = master.get_mech_groups_of_evaluation_framework("custom", project=project)
    return render_template(
        "evaluations/overview.html",
        callback="start_custom_evaluation",
        browser_name=browser,
        mech_groups=mech_groups,
        logs=log_printer.logs,
        extensions=extensions,
        cli_options=cli_options,
    )


@app.route("/eval/custom/<string:browser>", methods=["post"])
def start_custom_evaluation(browser):
    return generic_state_evaluation("custom", browser)


@socketio.on("ready")
def ready():
    return "OK"
    # THREAD.start()


@app.route("/error/<string:message>", methods=["get"])
def error(message):
    return "Error: %s" % message


def error_redirect(message):
    return redirect(url_for("error", message=message))


@app.route("/log", methods=["GET"])
def log_page():
    return render_template("base_with_logging.html", logs=log_printer.logs)


@app.route("/log", methods=["POST"])
def print_log():
    log_printer.print(request.form)
    return "200"


def get_available_extensions(browser: str):
    extensions = []
    folder_path = Config.get_extension_folder_path(browser)
    for _, _, files in os.walk(folder_path):
        extensions.extend(files)
    return extensions


def get_available_cli_options(browser: str):
    if browser == "chromium":
        return cli_options_chromium.get_all_cli_options()
    if browser == "firefox":
        return cli_options_firefox.get_all_cli_options()
    raise AttributeError("Unknown browser '%s'" % browser)


def get_associated_cli_argument(browser: str, cli_option: str):
    if browser == "chromium":
        return cli_options_chromium.get_associated_arguments(cli_option)
    if browser == "firefox":
        return cli_options_firefox.get_associated_arguments(cli_option)
    raise AttributeError("Unknown browser '%s'" % browser)


if __name__ == "__main__":
    # Configure flask logger
    filer_handler = logging.handlers.RotatingFileHandler("/app/logs/flask.log", mode='a', backupCount=2)
    filer_handler.setLevel(logging.DEBUG)
    logging.getLogger('werkzeug').addHandler(filer_handler)

    # Initialize log printer (prints log to web interface)
    log_printer = LogPrinter(socketio)

    # Master has to be initialized in parallel, otherwise requests from logger HTTPHandler cannot be handled by the server
    THREAD = threading.Thread(target=master.initialize)
    THREAD.start()

    # Debug is set to false because it would otherwise auto-reload (run the program twice)
    socketio.run(app, debug=False, host="0.0.0.0")
