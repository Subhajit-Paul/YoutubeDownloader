# YouTube Downloader

A simple desktop application for downloading YouTube videos and audio.

## Features

- Download YouTube videos in various resolutions
- Extract audio from YouTube videos
- Simple and intuitive user interface
- Cross-platform compatibility

## Download

Download the latest release for your platform:
- [Linux](https://github.com/Subhajit-Paul/YoutubeDownloader/releases/download/v1.0.0/youtube-downloader)
- [All Releases](https://github.com/Subhajit-Paul/youtube-downloader/releases)

## Prerequisites

This application requires FFmpeg to be installed on your system.

### Installing FFmpeg

#### Windows
1. Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html)
2. Extract the downloaded file
3. Add the bin folder to your system PATH

Or using Chocolatey:
```
choco install ffmpeg
```

#### macOS
Using Homebrew:
```
brew install ffmpeg
```

#### Linux (Ubuntu/Debian)
```
sudo apt update
sudo apt install ffmpeg
```

#### Linux (Fedora)
```
sudo dnf install ffmpeg
```

## Development Setup

### Clone the repository
```
git clone https://github.com/Subhajit-Paul/youtube-downloader.git
cd youtube-downloader
```

### Create and activate a virtual environment
```
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Install dependencies
```
pip install -r requirements.txt
```

## Building the Application

To create a standalone executable:

```
pyinstaller --noconsole --onefile --windowed --add-data "logo.png:." --name=youtube-downloader --icon=logo.png ytd.py
```

After the build process completes, you can find the executable in the `dist` folder.

## Usage

1. Launch the application
2. Enter a YouTube URL in the input field
3. Select your preferred download option (video or audio)
4. Choose the quality/resolution
5. Click the download button
6. Wait for the download to complete

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [FFmpeg](https://ffmpeg.org/) for media processing