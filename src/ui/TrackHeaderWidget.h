#pragma once

#include "core/Track.h"
#include <QWidget>
#include <QPushButton>
#include <QLabel>
#include <QSlider>

namespace ClipTune {

class TrackHeaderWidget : public QWidget {
    Q_OBJECT

public:
    explicit TrackHeaderWidget(TrackPtr track, QWidget* parent = nullptr);

    TrackPtr track() const { return m_track; }

    // Update from track data
    void updateFromTrack();

    // Height
    int trackHeight() const { return m_track ? m_track->height() : 80; }

signals:
    void muteToggled(bool muted);
    void soloToggled(bool solo);
    void volumeChanged(double volume);
    void trackSelected();

protected:
    void paintEvent(QPaintEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;

private slots:
    void onMuteClicked();
    void onSoloClicked();
    void onVolumeChanged(int value);

private:
    void setupUi();

    TrackPtr m_track;
    QLabel* m_nameLabel = nullptr;
    QPushButton* m_muteButton = nullptr;
    QPushButton* m_soloButton = nullptr;
    QSlider* m_volumeSlider = nullptr;
};

} // namespace ClipTune
