#pragma once

#include <QWidget>
#include <QImage>
#include <QMutex>

namespace ClipTune {

class PreviewWidget : public QWidget {
    Q_OBJECT

public:
    explicit PreviewWidget(QWidget* parent = nullptr);

    // Display frame
    void setFrame(const QImage& frame);
    void clearFrame();

    // Aspect ratio
    void setAspectRatio(double ratio) { m_aspectRatio = ratio; update(); }
    double aspectRatio() const { return m_aspectRatio; }

    // Video dimensions for aspect calculation
    void setVideoSize(int width, int height);

signals:
    void clicked();
    void doubleClicked();

protected:
    void paintEvent(QPaintEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseDoubleClickEvent(QMouseEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;

private:
    QRect calculateVideoRect() const;

    QImage m_frame;
    QImage m_scaledFrame;
    double m_aspectRatio = 16.0 / 9.0;
    mutable QMutex m_frameMutex;
    bool m_needsRescale = true;
};

} // namespace ClipTune
