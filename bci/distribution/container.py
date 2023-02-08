
from bci.params import WorkerParams


class Container:

    def __init__(self, params: WorkerParams, docker_object) -> None:
        self.params = params
        self.docker_object = docker_object

    def wait_until_done(self):
        self.docker_object.wait(condition="removed")
