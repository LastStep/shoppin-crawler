# shoppin.app Assignment

## Approach and Project Structure

The project implements a modular web scraping system for various e-commerce platforms. Here's a detailed breakdown of the architecture:

### Project Organization
```
logs/
output/
src/
├── base.py              # Base crawler class and common utilities
├── platforms/           # Platform-specific crawler implementations
│   ├── virgio.py
│   ├── westside.py
│   ├── nykaafashion.py
│   ├── tatacliq.py
│   └── inmyprime.py
├── utils/              # Helper utilities and common functions
main.py            # CLI entry point
```

### Technical Implementation
- **Base Crawler**: Implements core crawling functionality and common methods in `base.py`
- **Platform Crawlers**: Each platform has its dedicated crawler class that:
  - Implements platform-specific API endpoints and data extraction
  - Transforms platform-specific data into a common format
  - Manages rate limiting and error handling

### Key Features
- **API-First Approach**: Utilizes platform APIs where available for reliable data extraction
- **Modular Design**: Easy to add new platforms by extending the base crawler
- **Fault Tolerance**: Continues operation even if individual crawlers fail
- **Parallel Processing**: Supports concurrent execution of multiple crawlers
- **Data Persistence**: Saves data incrementally to CSV files in the output directory, even after error


## Installation

Before running the application, install the required dependencies:

```bash
pip install -r requirements.txt
```

## Running the Application

You can run the application from the command line using the following options:

```bash
# Run a specific crawler
python main.py --crawler <crawler_name>

# Run all available crawlers
python main.py --all

# Run all crawlers with specific number of workers
python main.py --all --workers 5
```

Available options:
- `--crawler` or `-c`: Specify a single crawler to run (e.g., virgio, westside)
- `--all` or `-a`: Run all available crawlers
- `--workers` or `-w`: Number of parallel workers when running all crawlers (default: 3)

Available Crawlers:
- `virgio` 
- `westside`
- `nykaafashion` 
- `tatacliq` 
- `inmyprime`

## Known Issues

- **Nykaa Crawler**: Currently failing due to user-agent header restrictions. The api blocks requests with default user-agent headers.
