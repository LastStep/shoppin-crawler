# Shopping Assignment

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
