#include "MainWindow.h"

MainWindow::MainWindow()
{
    setWindowTitle("Built with Golem!");

    message.setText("Built with Golem!");
    message.setAlignment(Qt::AlignCenter | Qt::AlignVCenter);
    message.setWordWrap(true);
    message.setStyleSheet(R"(
        QLabel {
            color: blue;
            font-size: 34px;
            font-weight: bold;
        }
    )");
    setCentralWidget(&message);

    resize(400, 300);
}