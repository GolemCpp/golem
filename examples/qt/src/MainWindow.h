#pragma once

#include <QMainWindow>
#include <QLabel>

class MainWindow : public QMainWindow
{
    Q_OBJECT
    
public:
    MainWindow();

private:
    QLabel message { this };
};