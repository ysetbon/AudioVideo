#include "TrackHeaderWidget.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPainter>
#include <QMouseEvent>

namespace ClipTune {

TrackHeaderWidget::TrackHeaderWidget(TrackPtr track, QWidget* parent)
    : QWidget(parent)
    , m_track(track)
{
    setupUi();
    updateFromTrack();
}

void TrackHeaderWidget::setupUi()
{
    setFixedWidth(150);
    setMinimumHeight(60);

    auto* mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(5, 5, 5, 5);
    mainLayout->setSpacing(4);

    // Track name
    m_nameLabel = new QLabel(this);
    m_nameLabel->setStyleSheet("QLabel { color: white; font-weight: bold; }");
    mainLayout->addWidget(m_nameLabel);

    // Buttons row
    auto* buttonLayout = new QHBoxLayout();
    buttonLayout->setSpacing(2);

    m_muteButton = new QPushButton("M", this);
    m_muteButton->setFixedSize(24, 24);
    m_muteButton->setCheckable(true);
    m_muteButton->setToolTip("Mute");
    m_muteButton->setStyleSheet(
        "QPushButton { background: #444; color: white; border: 1px solid #666; border-radius: 3px; }"
        "QPushButton:checked { background: #c44; }"
    );
    connect(m_muteButton, &QPushButton::clicked, this, &TrackHeaderWidget::onMuteClicked);
    buttonLayout->addWidget(m_muteButton);

    m_soloButton = new QPushButton("S", this);
    m_soloButton->setFixedSize(24, 24);
    m_soloButton->setCheckable(true);
    m_soloButton->setToolTip("Solo");
    m_soloButton->setStyleSheet(
        "QPushButton { background: #444; color: white; border: 1px solid #666; border-radius: 3px; }"
        "QPushButton:checked { background: #4a4; }"
    );
    connect(m_soloButton, &QPushButton::clicked, this, &TrackHeaderWidget::onSoloClicked);
    buttonLayout->addWidget(m_soloButton);

    buttonLayout->addStretch();
    mainLayout->addLayout(buttonLayout);

    // Volume slider
    m_volumeSlider = new QSlider(Qt::Horizontal, this);
    m_volumeSlider->setRange(0, 100);
    m_volumeSlider->setValue(100);
    m_volumeSlider->setToolTip("Volume");
    connect(m_volumeSlider, &QSlider::valueChanged, this, &TrackHeaderWidget::onVolumeChanged);
    mainLayout->addWidget(m_volumeSlider);

    mainLayout->addStretch();
}

void TrackHeaderWidget::updateFromTrack()
{
    if (!m_track) return;

    m_nameLabel->setText(m_track->name());
    m_muteButton->setChecked(m_track->isMuted());
    m_soloButton->setChecked(m_track->isSolo());
    m_volumeSlider->setValue(static_cast<int>(m_track->volume() * 100));

    setFixedHeight(m_track->height());
}

void TrackHeaderWidget::paintEvent(QPaintEvent* /*event*/)
{
    QPainter painter(this);

    // Background based on track type
    QColor bgColor = (m_track && m_track->type() == TrackType::Audio)
                     ? QColor(45, 55, 65)
                     : QColor(55, 65, 45);

    painter.fillRect(rect(), bgColor);

    // Right border
    painter.setPen(QColor(30, 30, 35));
    painter.drawLine(width() - 1, 0, width() - 1, height());

    // Bottom border
    painter.drawLine(0, height() - 1, width(), height() - 1);
}

void TrackHeaderWidget::mousePressEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        emit trackSelected();
    }
    QWidget::mousePressEvent(event);
}

void TrackHeaderWidget::onMuteClicked()
{
    if (m_track) {
        m_track->setMuted(m_muteButton->isChecked());
        emit muteToggled(m_track->isMuted());
    }
}

void TrackHeaderWidget::onSoloClicked()
{
    if (m_track) {
        m_track->setSolo(m_soloButton->isChecked());
        emit soloToggled(m_track->isSolo());
    }
}

void TrackHeaderWidget::onVolumeChanged(int value)
{
    if (m_track) {
        m_track->setVolume(value / 100.0);
        emit volumeChanged(m_track->volume());
    }
}

} // namespace ClipTune
