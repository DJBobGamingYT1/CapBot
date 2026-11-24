from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *

import main
from pygame import mixer
import time
import threading

class ChatView(QScrollArea):
    def __init__(self):
        super().__init__()
        container = QWidget()
        self.messageLayout = QVBoxLayout(container)
        self.messageLayout.addStretch()

        self.setWidget(container)
        self.setWidgetResizable(True)

        self.messages = []
        self.bubbleUserStylesheet = """
            QLabel {
                background-color: #3b454f;
                color: #ffffff;
                border-radius: 10px;
                border-top-right-radius: 5px;
                padding: 8px 12px;
            }
        """

        self.bubbleBotStylesheet = """
            QLabel {
                background-color: #5faefc;
                color: #000000;
                border-radius: 10px;
                border-top-left-radius: 5px;
                padding: 8px 12px;
            }
        """

    def add_message(self, sender, text, is_user=False):
        row = QHBoxLayout()
        bubble = QLabel(f"##### {sender}\n{text}")
        bubble.setWordWrap(True)
        bubble.setTextFormat(Qt.TextFormat.MarkdownText)
        bubble.setOpenExternalLinks(True)

        wrapper = QWidget()
        wrapper.setLayout(row)

        if is_user:
            row.addStretch()

            wrapper.setStyleSheet(self.bubbleUserStylesheet)
            bubble.setAlignment(Qt.AlignmentFlag.AlignRight)

            row.addWidget(bubble)
        else:
            wrapper.setStyleSheet(self.bubbleBotStylesheet)
            bubble.setAlignment(Qt.AlignmentFlag.AlignLeft)

            row.addWidget(bubble)
            row.addStretch()

        self.messageLayout.addWidget(
            wrapper
        )

        self.messages.append((wrapper, row, bubble))
        print(self.messages)

    def change_message(self, index, text):
        if self.messages[index] == None:
            return
        
        wrapper, row, bubble = self.messages[index]

        bubble.setText(bubble.text().split("\n")[0] + "\n" + text)

    def get_message_text(self, index):
        if self.messages[index] == None:
            return
                
        wrapper, row, bubble = self.messages[index]

        finalBubbleText = bubble.text().split("\n")
        finalBubbleText.pop(0)

        return " ".join(finalBubbleText)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        main.__init__()
        self.setWindowTitle("DJBot app - New Chat")
        self.drawUI()

    def drawUI(self):
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)

        self.mainLayout = QVBoxLayout()
        self.centralWidget.setLayout(self.mainLayout)

        self.chatView = ChatView()
        self.chatView.setBaseSize(100, 100)
        self.mainLayout.addWidget(self.chatView, 100)

        self.userTextboxLayout = QHBoxLayout()
        self.mainLayout.addLayout(self.userTextboxLayout, 1)

        self.userTextbox = QTextEdit()
        self.sendButton = QPushButton("Send")

        self.userTextbox.setBaseSize(100, 25)

        self.sendButton.clicked.connect(lambda: self.sendMessageToAI(self.userTextbox.toPlainText()))

        self.userTextboxLayout.addWidget(self.userTextbox)
        self.userTextboxLayout.addWidget(self.sendButton)

    def closeEvent(self, event):
        main.save_chat_history()

    def onAIResponded(self, response):
        self.chatView.change_message(-1, "")

        #for char in response.text:
        #    self.chatView.change_message(-1, self.chatView.get_message_text(-1) + char)
        
        self.chatView.change_message(-1, response.text)

        self.userTextbox.setEnabled(True)

    def sendMessageToAI(self, message):
        self.chatView.add_message("User", message, True)

        self.chatView.add_message("DJBot", "generating...\nwait cuz im generating my message right now", False)

        self.userTextbox.setEnabled(False)
        threading.Thread(target=lambda: main.talk_to_ai(message, self.onAIResponded)).start()

        self.userTextbox.clear()

if __name__ == "__main__":
    app = QApplication([])
    ui = MainWindow()
    ui.show()
    app.exec()