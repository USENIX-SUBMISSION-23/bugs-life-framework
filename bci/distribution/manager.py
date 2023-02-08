import logging
import os
import time
import threading
import docker
import docker.errors
from queue import Queue
from typing import Callable
from bci.params import WorkerParams


class ContainerManager:
    def __init__(self, max_nb_of_containers) -> None:
        self.logger = logging.getLogger("bci")
        self.max_nb_of_containers = max_nb_of_containers
        self.container_id_pool = Queue(maxsize=max_nb_of_containers)
        for i in range(max_nb_of_containers):
            self.container_id_pool.put(i)
        self.client = docker.from_env()

    def start_container(self, params: WorkerParams, cb: Callable, blocking_wait=True) -> None:
        while (
            blocking_wait
            and self.get_nb_of_running_worker_containers() >= self.max_nb_of_containers
        ):
            time.sleep(5)
        container_id = self.container_id_pool.get()
        command = f"./worker.sh {self.stringify_params(params)}".split(" ")

        def start_container_thread():
            container_name = f"bci_worker_{container_id}"
            try:
                # Sometimes, it takes a while for Docker to remove the container
                while True:
                    # Get all containers with same name
                    active_containers = self.client.containers.list(
                        all=True,
                        ignore_removed=True,
                        filters={
                            "name": f"^/{container_name}$"  # The exact name has to match
                        }
                    )
                    # Break loop if no container with same name is active
                    if not active_containers:
                        break
                    # Remove all containers with same name (never higher than 1 in practice)
                    for container in active_containers:
                        self.logger.info(f"Removing old container '{container.attrs['Name']}' to start new one")
                        container.remove(force=True)
                self.client.containers.run(
                    "bci_worker",
                    name=container_name,
                    hostname=container_name,
                    shm_size="2gb",
                    network="bci_net",
                    mem_limit="1g",  # To prevent one container from consuming multiple gigs of memory (was the case for a Firefox evaluation)
                    detach=False,
                    remove=True,
                    labels=["bci_worker"],
                    command=command,
                    environment={
                        "bci_mongo_host": os.getenv("bci_mongo_host"),
                        "bci_mongo_database": os.getenv("bci_mongo_database"),
                        "bci_mongo_username": os.getenv("bci_mongo_username"),
                        "bci_mongo_password": os.getenv("bci_mongo_password"),
                    },
                    volumes=[
                        os.path.join(os.getenv("host_pwd"), "binaries/chromium/artisanal") + ":/app/binaries/chromium/artisanal",
                        os.path.join(os.getenv("host_pwd"), "binaries/firefox/artisanal") + ":/app/binaries/firefox/artisanal",
                        os.path.join(os.getenv("host_pwd"), "drivers/firefox") + ":/app/drivers/firefox",
                        os.path.join(os.getenv("host_pwd"), "drivers/chromium") + ":/app/drivers/chromium",
                        os.path.join(os.getenv("host_pwd"), "snapshots") + ":/app/snapshots",
                        os.path.join(os.getenv("host_pwd"), "extensions/chromium") + ":/app/extensions/chromium",
                        os.path.join(os.getenv("host_pwd"), "extensions/firefox") + ":/app/extensions/firefox",
                        os.path.join(os.getenv("host_pwd"), "browser-repos/chromium/src") + ":/browser-repos/chromium",
                        os.path.join(os.getenv("host_pwd"), "browser-repos/firefox-release") + ":/browser-repos/firefox-release",
                        os.path.join(os.getenv("host_pwd"), "logs") + ":/app/logs",
                        "/dev/shm:/dev/shm",
                    ],
                )
                self.logger.debug(f"Container '{container_name}' started with command '{command}'")
                cb()
            except docker.errors.APIError:
                self.logger.error(f"Could not run container '{container_name}' or container was unexpectedly removed", exc_info=True)
            finally:
                self.container_id_pool.put(container_id)

        thread = threading.Thread(target=start_container_thread)
        thread.start()
        # To avoid race-condition where more than max containers are started
        time.sleep(5)

    def get_nb_of_running_worker_containers(self):
        return len(self.get_runnning_containers())

    def get_runnning_containers(self):
        return self.client.containers.list(filters={"label": "bci_worker", "status": "running"}, ignore_removed=True)

    def wait_until_all_containers_are_done(self):
        while True:
            if self.get_nb_of_running_worker_containers() == 0:
                break
            time.sleep(5)

    @staticmethod
    def stringify_params(params: WorkerParams) -> str:
        param_string = (
            f"--framework-name {params.evaluation_framework_name} --automation {params.automation} "
            + f"--browser {params.browser} --state_id {params.state_id} --config {params.configuration_option}"
        )
        if params.mech_id:
            param_string += f" --mech_id {params.mech_id}"
        param_string += " --mech_groups " + " --mech_groups ".join(params.mech_groups)
        if params.extension_name:
            param_string += f"--extension_file {params.extension_name}"
        if len(params.additional_cli_options) > 0:
            param_string += " --browser_cli_options" + " --browser_cli_options".join(
                params.additional_cli_options
            )
        if params.cookie_name:
            param_string += f" --cookie_name {params.cookie_name}"
        return param_string
