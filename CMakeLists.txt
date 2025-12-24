cmake_minimum_required(VERSION 3.20)
project(ClipTune VERSION 0.1.0 LANGUAGES CXX)

# C++20 standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Qt configuration
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

# Find Qt6
find_package(Qt6 REQUIRED COMPONENTS
    Widgets
    Multimedia
    Concurrent
)

# Find FFmpeg via vcpkg
find_package(FFMPEG REQUIRED)

# Find swresample and swscale separately (not always included in FFMPEG_LIBRARIES)
find_package(PkgConfig REQUIRED)
pkg_check_modules(SWRESAMPLE REQUIRED libswresample)
pkg_check_modules(SWSCALE REQUIRED libswscale)

# Collect all source files
set(CORE_SOURCES
    src/core/Project.cpp
    src/core/Track.cpp
    src/core/Clip.cpp
    src/core/UndoStack.cpp
    src/core/Commands.cpp
)

set(MEDIA_SOURCES
    src/media/FfmpegInit.cpp
    src/media/Demuxer.cpp
    src/media/AudioDecoder.cpp
    src/media/VideoDecoder.cpp
    src/media/Resampler.cpp
    src/media/Scaler.cpp
    src/media/FrameQueues.cpp
)

set(AUDIO_SOURCES
    src/audio/AudioEngine.cpp
    src/audio/AudioRingBuffer.cpp
    src/audio/Mixer.cpp
    src/audio/FadeDSP.cpp
)

set(UI_SOURCES
    src/ui/MainWindow.cpp
    src/ui/TimelineWidget.cpp
    src/ui/PreviewWidget.cpp
    src/ui/TrackHeaderWidget.cpp
    src/ui/ClipItem.cpp
    src/ui/RulerWidget.cpp
    src/ui/WaveformCache.cpp
)

set(RENDER_SOURCES
    src/render/ExportJob.cpp
    src/render/Mp4Muxer.cpp
)

set(APP_SOURCES
    src/app/Application.cpp
)

# Create executable
add_executable(ClipTune
    src/main.cpp
    ${CORE_SOURCES}
    ${MEDIA_SOURCES}
    ${AUDIO_SOURCES}
    ${UI_SOURCES}
    ${RENDER_SOURCES}
    ${APP_SOURCES}
)

# Include directories
target_include_directories(ClipTune PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${FFMPEG_INCLUDE_DIRS}
)

# Link directories (needed for vcpkg FFmpeg)
target_link_directories(ClipTune PRIVATE
    ${FFMPEG_LIBRARY_DIRS}
)

# Link libraries
target_link_libraries(ClipTune PRIVATE
    Qt6::Widgets
    Qt6::Multimedia
    Qt6::Concurrent
    ${FFMPEG_LIBRARIES}
    ${SWRESAMPLE_LIBRARIES}
    ${SWSCALE_LIBRARIES}
)

# Platform-specific settings
if(WIN32)
    # Windows-specific: set subsystem to windows for release, console for debug
    set_target_properties(ClipTune PROPERTIES
        WIN32_EXECUTABLE $<NOT:$<CONFIG:Debug>>
    )
endif()

# Install rules
install(TARGETS ClipTune
    RUNTIME DESTINATION bin
)

# Copy Qt plugins on Windows (for development)
if(WIN32)
    # Use windeployqt in a post-build step for development
    add_custom_command(TARGET ClipTune POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E echo "Run windeployqt manually for deployment"
    )
endif()
