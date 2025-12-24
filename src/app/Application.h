#pragma once

#include <QApplication>
#include <memory>

namespace ClipTune {

class MainWindow;

class Application : public QApplication {
    Q_OBJECT

public:
    Application(int& argc, char** argv);
    ~Application() override;

    // Get application instance
    static Application* instance();

    // Get main window
    MainWindow* mainWindow() const { return m_mainWindow.get(); }

    // Initialize application
    bool init();

    // Application info
    static QString appName() { return QStringLiteral("ClipTune"); }
    static QString appVersion() { return QStringLiteral("0.1.0"); }
    static QString appOrganization() { return QStringLiteral("ClipTune"); }

private:
    void initFfmpeg();
    void setupStyle();

    std::unique_ptr<MainWindow> m_mainWindow;
};

} // namespace ClipTune
