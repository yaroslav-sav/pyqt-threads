import json
import socket
import struct
import sys
from queue import Queue

from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


HOST = "127.0.0.1"
PORT = 50505


class NetCom:
    def __init__(self, sock):
        self.sock = sock

    @staticmethod
    def _recv_exact(sock, size):
        chunks = []
        received = 0
        while received < size:
            chunk = sock.recv(size - received)
            if not chunk:
                return None
            chunks.append(chunk)
            received += len(chunk)
        return b"".join(chunks)

    def recv(self):
        header = self._recv_exact(self.sock, 4)
        if header is None:
            return None

        payload_size = struct.unpack("!I", header)[0]
        payload = self._recv_exact(self.sock, payload_size)
        if payload is None:
            return None

        return json.loads(payload.decode("utf-8"))

    def send(self, message):
        payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = struct.pack("!I", len(payload))
        self.sock.sendall(header + payload)


class ReceiveThread(QThread):
    message_received = pyqtSignal(dict)
    def __init__(self, net):
        super().__init__()
        self.net = net
        self.message_shutdown = {
            "type": "system",
            "text": "disconnection"
        }

    def run(self):
        while True:
            try:
                message = self.net.recv()
                if message is None:
                    self.message_received.emit(self.message_shutdown)
                    break
                self.message_received.emit(message)
            except OSError:
                self.message_received.emit(self.message_shutdown)
                break

class SendThread(QThread):
    def __init__(self, net):
        super().__init__()
        self.net = net
        self.queue = Queue()

    def send(self, message):
        self.queue.put(message)

    def stop(self):
        self.queue.put(None)

    def run(self):
        while True:
            message = self.queue.get()
            if message is None:
                break
            try:
                self.net.send(message)
            except OSError:
                break


class MainWindow(QMainWindow):
    def __init__(self, net):
        super().__init__()
        self.net = net

        self.setWindowTitle("PyQt6 network chat")
        self.resize(560, 420)

        self.history = QTextEdit()
        self.history.setReadOnly(True)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a message…")

        self.send_button = QPushButton("Send")
        self.status_label = QLabel()
        self.set_connect()

        name_layout = QHBoxLayout()
        self.name_label = QLabel("Name:")
        self.name_input = QLineEdit()
        name_layout.addWidget(self.name_label)
        name_layout.addWidget(self.name_input)

        self.button_clear = QPushButton("Clear history")
        name_layout.addWidget(self.button_clear)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addLayout(name_layout)
        layout.addWidget(self.history)
        layout.addLayout(input_row)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self.send_button.clicked.connect(self.on_send_clicked)
        self.input.returnPressed.connect(self.on_send_clicked)
        self.button_clear.clicked.connect(self.clear_history)

        self.receive_thread = ReceiveThread(self.net)
        self.receive_thread.message_received.connect(self.handle_message)
        self.receive_thread.start()

        self.send_thread = SendThread(self.net)
        self.send_thread.start()

    def on_send_clicked(self):
        text = self.input.text().strip()
        name = self.name_input.text().strip()
        if not text:
            return

        if not name:
            self.status_label.setText("Type your name")
            return

        self.send_thread.send({
            "type": "chat",
            "username": name,
            "text": text,
        })

        self.input.clear()


    def handle_message(self, message):
        if message.get("type") == "chat":
            text = message.get("text", "")
            name = message.get("username", "")
            self.history.append(f"{name}: {text}")
        elif message.get("type") == "system":
            text = message.get("text", "")
            if text == "disconnection":
                self.set_disconnect()
            self.history.append(f"[Система] {text}")


    def clear_history(self):
        self.history.clear()


    def set_disconnect(self):
        self.status_label.setText("Disconnected")


    def set_connect(self):
        self.status_label.setText("Connected")


def main():
    app = QApplication(sys.argv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except OSError as exc:
        print(f"Could not connect to server at {HOST}:{PORT}: {exc}")
        print("Run server.py first, then start main.py.")
        return

    net = NetCom(sock)
    window = MainWindow(net)
    window.show()

    exit_code = app.exec()
    window.send_thread.stop()
    window.send_thread.wait(1000)
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()