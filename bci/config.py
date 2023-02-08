import os
import sys
import yaml
import logging
import logging.handlers


class Config:

    evaluation_jar_path = None
    custom_test_folder = None
    custom_page_folder = None

    firefox_repo_path = None
    chromium_repo_path = None

    firefox_bin_folder_path = None
    chromium_bin_folder_path = None

    firefox_data_folder_path = None
    chromium_data_folder_path = None

    firefox_driver_folder_path = None
    chromium_driver_folder_path = None

    firefox_extension_folder_path = None
    chromium_extension_folder_path = None

    @staticmethod
    def configure_loggers():
        hostname = os.getenv("HOSTNAME")

        # Configure bci_logger
        bci_logger = logging.getLogger("bci")
        bci_logger.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler()
        file_handler = logging.handlers.RotatingFileHandler(f"/app/logs/{hostname}.log", mode='a', backupCount=2)
        http_handler = CustomHTTPHandler("master:5000", "/log", method="POST", secure=False)

        stream_handler.setLevel(logging.DEBUG)
        file_handler.setLevel(logging.DEBUG)
        http_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(fmt='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s', datefmt='%d-%m-%Y %H:%M:%S')
        stream_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        http_handler.setFormatter(formatter)

        bci_logger.addHandler(stream_handler)
        bci_logger.addHandler(file_handler)
        bci_logger.addHandler(http_handler)

        # Configure web_logger
        web_logger = logging.getLogger("web_gui")
        web_logger.setLevel(logging.DEBUG)

        web_file_handler = logging.handlers.RotatingFileHandler("/app/logs/web_gui.log", mode='a', backupCount=2)
        web_http_handler = CustomHTTPHandler("host.docker.internal:5000", "/log", method="POST", secure=False)

        web_file_handler.setLevel(logging.DEBUG)
        web_http_handler.setLevel(logging.INFO)

        web_file_handler.setFormatter(formatter)
        web_http_handler.setFormatter(formatter)

        web_logger.addHandler(web_file_handler)
        web_logger.addHandler(web_http_handler)

        # Log uncaught exceptions
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            bci_logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

        sys.excepthook = handle_exception

        bci_logger.debug("Loggers initialized")

    @staticmethod
    def load_config():
        browsers = ["firefox", "chromium"]
        attributes = ["repo_path", "bin_folder_path", "data_folder_path", "driver_folder_path", "extension_folder_path"]

        curr_dir = os.path.dirname(os.path.realpath(__file__))
        yaml_path = os.path.join(os.path.dirname(curr_dir), "config.yaml")
        with open(yaml_path, 'r') as file:
            config = yaml.safe_load(file)

        Config.evaluation_jar_path = config["evaluation_jar"]
        Config.custom_test_folder = config["custom_test_folder"]
        Config.custom_page_folder = config["custom_page_folder"]

        for browser in browsers:
            if browser not in config:
                config.raise_config_error(browser)
            for attribute in attributes:
                if attribute in config[browser]:
                    setattr(Config, "%s_%s" % (browser, attribute), os.path.expanduser(config[browser][attribute]))
                else:
                    Config.raise_config_error("%s.%s" % (browser, attribute))

    @staticmethod
    def get_extension_folder_path(browser: str):
        if browser == "chromium":
            return Config.chromium_extension_folder_path
        if browser == "firefox":
            return Config.firefox_extension_folder_path
        raise AttributeError("Browser '%s' is not supported" % browser)

    @staticmethod
    def raise_config_error(attribute_name):
        raise AttributeError("No configuration found for %s" % attribute_name)


class CustomHTTPHandler(logging.handlers.HTTPHandler):

    def __init__(self, host: str, url: str, method: str = 'GET', secure: bool = False, credentials=None, context=None) -> None:
        super().__init__(host, url, method=method, secure=secure, credentials=credentials, context=context)
        self.hostname = os.getenv("HOSTNAME")

    def mapLogRecord(self, record):
        record_dict = super().mapLogRecord(record)
        record_dict["hostname"] = self.hostname
        return record_dict
