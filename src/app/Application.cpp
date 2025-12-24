#include "Application.h"
#include "ui/MainWindow.h"
#include "media/FfmpegInit.h"
#include <QStyleFactory>
#include <QPalette>
#include <QFont>

namespace ClipTune {

Application::Application(int& argc, char** argv)
    : QApplication(argc, argv)
{
    setApplicationName(appName());
    setApplicationVersion(appVersion());
    setOrganizationName(appOrganization());
}

Application::~Application() = default;

Application* Application::instance()
{
    return static_cast<Application*>(QCoreApplication::instance());
}

bool Application::init()
{
    // Initialize FFmpeg
    initFfmpeg();

    // Setup application style
    setupStyle();

    // Create main window
    m_mainWindow = std::make_unique<MainWindow>();
    m_mainWindow->show();

    return true;
}

void Application::initFfmpeg()
{
    ClipTune::initFfmpeg();
}

void Application::setupStyle()
{
    // Use Fusion style for consistent cross-platform appearance
    setStyle(QStyleFactory::create("Fusion"));

    // Dark color palette
    QPalette darkPalette;
    darkPalette.setColor(QPalette::Window, QColor(53, 53, 53));
    darkPalette.setColor(QPalette::WindowText, Qt::white);
    darkPalette.setColor(QPalette::Base, QColor(35, 35, 35));
    darkPalette.setColor(QPalette::AlternateBase, QColor(53, 53, 53));
    darkPalette.setColor(QPalette::ToolTipBase, QColor(25, 25, 25));
    darkPalette.setColor(QPalette::ToolTipText, Qt::white);
    darkPalette.setColor(QPalette::Text, Qt::white);
    darkPalette.setColor(QPalette::Button, QColor(53, 53, 53));
    darkPalette.setColor(QPalette::ButtonText, Qt::white);
    darkPalette.setColor(QPalette::BrightText, Qt::red);
    darkPalette.setColor(QPalette::Link, QColor(42, 130, 218));
    darkPalette.setColor(QPalette::Highlight, QColor(42, 130, 218));
    darkPalette.setColor(QPalette::HighlightedText, Qt::black);
    darkPalette.setColor(QPalette::Disabled, QPalette::Text, QColor(127, 127, 127));
    darkPalette.setColor(QPalette::Disabled, QPalette::ButtonText, QColor(127, 127, 127));

    setPalette(darkPalette);

    // Set stylesheet for additional customization
    setStyleSheet(
        "QToolTip { color: #ffffff; background-color: #2a2a2a; border: 1px solid #767676; }"
        "QMenuBar { background-color: #353535; }"
        "QMenuBar::item:selected { background-color: #454545; }"
        "QMenu { background-color: #353535; border: 1px solid #454545; }"
        "QMenu::item:selected { background-color: #2a82da; }"
        "QScrollBar:vertical { background: #2a2a2a; width: 12px; }"
        "QScrollBar:horizontal { background: #2a2a2a; height: 12px; }"
        "QScrollBar::handle { background: #5a5a5a; border-radius: 4px; }"
        "QScrollBar::handle:hover { background: #6a6a6a; }"
        "QSplitter::handle { background: #353535; }"
    );
}

} // namespace ClipTune
