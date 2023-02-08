import os
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne
from pymongo.errors import ServerSelectionTimeoutError
from bci.version_control.version_control import RepoState
from bci.params import DatabaseParams

# pylint: disable=global-statement
CLIENT = None
DB = None


class MongoDB(ABC):
    instance = None

    binary_availability_collection_names = {
        "chromium": "chromium_binary_availability",
        "firefox": "firefox_central_binary_availability"
    }

    def __init__(self):
        self.client = CLIENT
        self.db = DB
        self.logger = logging.getLogger("bci")

    @classmethod
    def get_instance(cls):
        if cls.instance is None:
            cls.instance = cls()
        return cls.instance

    @staticmethod
    def connect():
        global CLIENT, DB
        if not os.environ['bci_mongo_host'] or \
                not os.environ['bci_mongo_database'] or \
                not os.environ['bci_mongo_username'] or \
                not os.environ['bci_mongo_password']:
            raise AttributeError("Could not find MongoDB credentials in system environment")
        host = os.environ['bci_mongo_host']
        database = os.environ['bci_mongo_database']
        username = os.environ['bci_mongo_username']
        password = os.environ['bci_mongo_password']

        CLIENT = MongoClient(
            host=host,
            port=27017,
            username=username,
            password=password,
            authsource=database,
            retryWrites=False)
        # Force connection to check whether MongoDB server is reachable
        try:
            CLIENT.server_info()
            DB = CLIENT[database]
            logging.getLogger("bci").debug("Connected to database")
        except ServerSelectionTimeoutError as e:
            logging.getLogger("bci").critical("Could not connect to database", exc_info=True)
            raise ServerException from e

    @staticmethod
    def disconnect():
        global CLIENT, DB
        CLIENT.close()
        CLIENT = None
        DB = None

    def store_data(self, automation: str, browser_name: str, browser_version: str, driver_version: str, browser_setting: str,
                   extension_name: str, additional_cli_options: list, state: RepoState, mech_group: str, json_data,
                   is_dirty_evaluation: bool):
        """
        Stores the evaluation data for the browser state identified by the given arguments.

        :param browser_name:
        :param browser_version:
        :param driver_version:
        :param browser_setting:
        :param extension_name:
        :param additional_cli_options
        :param state:
        :param mech_group:
        :param json_data:
        :param is_dirty_evaluation:
        :return: None
        """
        collection = self.get_data_collection(browser_name)

        document = {
            'browser_automation': automation,
            'browser_version': browser_version,
            'padded_browser_version': MongoDB.get_padded_version(browser_version),
            'browser_config': browser_setting,
            'state_id': int(state.id) if state.id.isdigit() else state.id,
            'mech_group': mech_group,
            'results': json_data,
            'dirty': is_dirty_evaluation,
            'ts': str(datetime.now(timezone.utc).replace(microsecond=0))
        }
        if driver_version:
            document["driver_version"] = driver_version

        if browser_name == "firefox":
            if state.version:
                document["release"] = True
                document["build_id"] = "release"
            else:
                build_id = self.get_build_id_firefox(state.id)
                if build_id is None:
                    document["artisanal"] = True
                    document["build_id"] = "artisanal"
                else:
                    document["build_id"] = build_id
            if state.release_revision_id is not None:
                document["release_revision_id"] = state.release_revision_id

        if extension_name:
            document["extension_name"] = extension_name

        if len(additional_cli_options) > 0:
            document["additional_cli_options"] = additional_cli_options

        collection.insert_one(document)

    def get_data(
            self, automation: str, browser_name: str, browser_setting: str, extension_name: str,
            additional_cli_options: list, mech_group: str, mech_id: str, state: RepoState, cookie_name: str):
        """
        Returns True if the mechanism associated with the given mech_id initiated a request, in an evaluation determined
        by the other parameters. Returns False if no request was initiated. Returns None if the mechanism associated
        with the given mech_id was not covered in the evaluation.

        :param browser_name: name of the used browser
        :param browser_setting: name of the used browser setting
        :param extension_name: name of the extension file
        :param additional_cli_options
        :param mech_group: name of the mechanism group that was evaluated (if the given mech_id is not included in this
        group, this method should always return None)
        :param mech_id: mechanism id
        :param state: state of the browser binary
        :param cookie_name: name of the cookie, if specified
        :return: True if the mechanism associated with the given mech_id initiated a request, in an evaluation determined
        by the other parameters. False if no request was initiated. None if the mechanism associated
        with the given mech_id was not covered in the evaluation.
        """
        collection = self.get_data_collection(browser_name)
        search_criteria =\
            {'state_id': int(state.id) if state.id.isdigit() else state.id,
             'browser_automation': automation,
             'browser_config': browser_setting,
             'mech_group': mech_group}
        if extension_name:
            search_criteria["extension_name"] = extension_name
        if len(additional_cli_options) > 0:
            search_criteria["additional_cli_options"] = {"$size": len(additional_cli_options), "$all": additional_cli_options}
        document = collection.find_one(search_criteria)
        if document is None:
            raise AttributeError("Could not find document for '%s'" % str(search_criteria))
        if "results" not in document:
            return None
        if document["results"] is None:
            return None
        if mech_id not in document["results"]:
            return None
        output_line = document["results"][mech_id]

        if cookie_name is None:
            return "true" in output_line
        return cookie_name in output_line

    def has_data(self, automation: str, browser_name: str, browser_setting: str, extension_name: str,
                 additional_cli_options: str, mech_group: str, state: RepoState):
        collection = self.get_data_collection(browser_name)
        search_criteria =\
            {'state_id': int(state.id) if state.id.isdigit() else state.id,
             'browser_automation': automation,
             'browser_config': browser_setting,
             'mech_group': mech_group}
        if extension_name:
            search_criteria["extension_name"] = extension_name
        if len(additional_cli_options) > 0:
            search_criteria["additional_cli_options"] = {"$size": len(additional_cli_options), "$all": additional_cli_options}
        document = collection.find_one(search_criteria)
        return document is not None

    def get_data_with_params(self, params: DatabaseParams):
        collection = self.get_data_collection(params.browser_name)
        query = params.to_mongodb_query()
        document = collection.find_one(query)
        if document is None:
            raise AttributeError("Could not find document for '%s'" % str(query))
        if "results" not in document:
            return None
        if document["results"] is None:
            return None
        if params.mech_id not in document["results"]:
            return False
        output_line = document["results"][params.mech_id]

        if params.cookie_name is None:
            return "true" in output_line
        return params.cookie_name in output_line

    def has_all_data_with_params(self, params: DatabaseParams):
        collection = self.get_data_collection(params.browser_name)
        query = params.to_mongodb_query()
        nb_of_documents = collection.count_documents(query)
        return nb_of_documents == len(params.mech_groups)

    @abstractmethod
    def get_data_collection(self, browser_name: str):
        pass

    @staticmethod
    def get_binary_availability_collection(browser_name: str):
        collection_name = MongoDB.binary_availability_collection_names[browser_name]
        if collection_name not in DB.collection_names():
            raise AttributeError("Collection '%s' not found in database" % collection_name)
        return DB[collection_name]

    # Caching of online binary availability

    @staticmethod
    def has_binary_available_online(browser: str, state_id: str):
        collection = MongoDB.get_binary_availability_collection(browser)
        document = collection.find_one({"state_id": int(state_id) if state_id.isdigit() else state_id})
        if document is None:
            return None
        return document["binary_online"]

    @staticmethod
    def get_stored_binary_availability(browser):
        collection = MongoDB.get_binary_availability_collection(browser)
        result = collection.find(
            {
                "binary_online": True
            },
            {
                "_id": False,
                "state_id": True,
            }
        )
        if browser == "firefox":
            result.sort('build_id', -1)
        return result

    @staticmethod
    def get_binary_url(browser: str, state_id: str):
        collection = MongoDB.get_binary_availability_collection(browser)
        result = collection.find_one(
            {
                "state_id": int(state_id) if state_id.isdigit() else state_id
            },
            {
                "_id": False,
                "url": True
            }
        )
        if len(result) == 0:
            raise AttributeError("No entry found for state_id '%s'" % state_id)
        return result["url"]

    @staticmethod
    def store_binary_availability_online_cache(browser: str, state_id: str, binary_online: bool, url: str = None):
        collection = MongoDB.get_binary_availability_collection(browser)
        collection.update_one(
            {
                "state_id": int(state_id) if state_id.isdigit() else state_id
            },
            {
                "$set":
                {
                    "state_id": int(state_id) if state_id.isdigit() else state_id,
                    "binary_online": binary_online,
                    "url": url,
                    "ts": str(datetime.now(timezone.utc).replace(microsecond=0))
                }
            },
            upsert=True
        )

    @staticmethod
    def store_binary_availability_online_cache_firefox(upsert_data):
        collection = MongoDB.get_binary_availability_collection("firefox")

        bulk_update = []
        for attributes in upsert_data:
            update = UpdateOne(
                {
                    "state_id": attributes["changeset_id"]
                },
                {
                    "$set": {
                        "state_id": attributes["changeset_id"],
                        "binary_online": attributes["binary_online"],
                        "url": attributes["binary_url"],
                        'build_id': attributes["build_id"],
                        "ts": str(datetime.now(timezone.utc).replace(microsecond=0))
                    }
                }, upsert=True)
            bulk_update.append(update)
        if len(bulk_update) > 0:
            collection.bulk_write(bulk_update)

    @staticmethod
    def get_build_id_firefox(state_id):
        collection = MongoDB.get_binary_availability_collection("firefox")

        result = collection.find_one({
            "state_id": state_id
        }, {
            "_id": False,
            "build_id": 1
        })
        # Result can only be None if the binary associated with the state_id is artisanal:
        # This state_id will not be included in the binary_availability_collection and not have a build_id.
        if result is None or len(result) == 0:
            return None
        return result["build_id"]

    @staticmethod
    def get_padded_version(version: str):
        padding_target = 4
        padded_version = []
        for sub in version.split("."):
            if len(sub) > padding_target:
                raise AttributeError("Version '%s' is too big to be padded" % version)
            padded_version.append("0" * (padding_target - len(sub)) + sub)
        return ".".join(padded_version)


class ServerException(Exception):
    pass
