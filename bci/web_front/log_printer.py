class LogPrinter:
    def __init__(self, socketio):
        self.socketio = socketio
        self.logs = []

    def print(self, log_data):
        self.push_log_entry(f"[{log_data['asctime']}] - [{log_data['levelname']}] - [{log_data['hostname']}] - {log_data['name']}: {log_data['msg']}")

    def push_log_entry(self, message):
        entry = {"message": message}
        self.logs.append(entry)
        self.socketio.emit("log", entry)
        print(message)
