"""Main entry point for WaveSync application."""

from .wavesync_app import WaveSyncApp


def run():
    """Run the WaveSync application."""
    app = WaveSyncApp()
    app.run()


if __name__ == '__main__':
    run()
