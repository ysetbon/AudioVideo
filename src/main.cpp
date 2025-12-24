#include "app/Application.h"
#include <QDebug>

int main(int argc, char* argv[])
{
    // Enable high DPI scaling
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
    QCoreApplication::setAttribute(Qt::AA_UseHighDpiPixmaps);
#endif

    ClipTune::Application app(argc, argv);

    if (!app.init()) {
        qCritical() << "Failed to initialize application";
        return 1;
    }

    return app.exec();
}
