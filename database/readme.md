# ECLI Data Ingestion & Analysis Pipeline (Dockerized)

This project provides a professional-grade, high-performance pipeline for ingesting a large corpus of Portuguese ECLI (European Case Law Identifier) judicial decisions from JSON format into a PostgreSQL database. The entire environment is containerized with Docker for maximum portability, consistency, and ease of setup.

Following ingestion, a powerful analysis tool inspects the corpus to generate critical, data-driven insights and recommendations for building a subsequent Retrieval-Augmented Generation (RAG) system.

## 🌟 Key Features

- **🚀 Dockerized Environment**: One-command setup with `docker-compose` for PostgreSQL, pgAdmin, and the Python processing environment.
- **⚡ High-Performance Ingestion**: The `json_to_postgres_loader.py` script uses **multiprocessing** to leverage all CPU cores, dramatically reducing the time to load hundreds of thousands of documents.
- **📊 Advanced Monitoring**: The loader provides real-time progress, performance metrics (files/sec), ETA, memory usage monitoring, and detailed error reporting.
- **🧠 Intelligent Corpus Analysis**: The `corpus_analyzer.py` script queries the populated database to provide crucial data for RAG system design, including text length statistics, metadata completeness, and vector storage estimations.
- **🔩 Robust & Idempotent**: The ingestion process can be safely re-run. It uses an `ON CONFLICT` clause to avoid duplicating records.
- **🧼 Clean Slate Utility**: Includes a `fresh_database_setup.py` script to completely wipe and re-initialize the database schema, perfect for development and testing.
- **✅ Pre-Flight Checks**: Utility scripts (`test_connection.py`, `test_json_files.py`) are provided to validate the environment setup before launching long-running processes.

## 🏗️ System Architecture

The system is orchestrated by Docker Compose and consists of three main components:

1.  **PostgreSQL Container (`postgres`)**: The database server where all ECLI data is stored. It's configured with a persistent volume to ensure data is not lost when the container stops.
2.  **Application Environment (within `postgres` container)**: A Python 3 environment is installed directly into the PostgreSQL container, containing all necessary libraries and application scripts. This allows scripts to be run directly inside the container with access to the database.
3.  **pgAdmin Container (`pgadmin`)**: An optional web-based GUI for easily managing and querying the PostgreSQL database.

--- 

## ⚙️ Setup & Usage

### Method 1: Docker (Recommended)

This is the simplest and most reliable way to run the project.

**Prerequisites:**
- [Docker](https://www.docker.com/products/docker-desktop/) installed and running.
- Your 320,000+ JSON files placed in a local directory.

**Step 1: Configure the Environment**

1.  **Create a `.env` file** in the project root. Copy the contents from the provided `.env` example and **set your `DB_PASSWORD`**.
    ```dotenv
    DB_HOST=postgres
    DB_NAME=ecli_rag_db
    DB_USER=postgres
    DB_PASSWORD=YOUR_SECRET_PASSWORD_HERE
    DB_PORT=5432
    ```
    *Note: `DB_HOST` should be `postgres` when running with Docker, as that is the service name in `docker-compose.yml`.*

2.  **Mount your JSON files.** Open `docker-compose.yml` and edit the `postgres` service volumes to point to your local JSON directory. For example, if your JSONs are in `d:/jsons`, the line should look like this:
    ```yaml
    volumes:
      # ... other volumes
      - d:/jsons:/data/jsons:ro # Mount local JSONs as read-only
    ```

**Step 2: Build and Start Containers**

- **For Windows**: Simply run the provided batch script. It will build and start the containers for you.
  ```bash
  docker-setup.bat
  ```

- **For macOS/Linux**: Use `docker-compose` directly.
  ```bash
  docker-compose up --build -d
  ```

Your environment is now running! 
- **PostgreSQL** is available at `localhost:5432`.
- **pgAdmin** is available at `http://localhost:8080`.

**Step 3: Load Data into the Database**

Execute the loader script *inside* the running container. It will find the JSON files in `/data/jsons` (where you mounted them).

```bash
docker-compose exec postgres python /app/json_to_postgres_loader.py
```

You will see a detailed progress bar as it loads the data using multiple CPU cores.

**Step 4: Analyze the Corpus**

After the loading is complete, run the analyzer script.

```bash
docker-compose exec postgres python /app/corpus_analyzer.py
```

This will print a detailed analysis to the console and create a `corpus_analysis_report_{timestamp}.json` file inside the container at `/app`.


### Method 2: Manual (Local Installation)

Use this method if you prefer not to use Docker and want to run the scripts on your host machine.

**Prerequisites:**
- Python 3.8+
- PostgreSQL 12+

1.  **Install Python dependencies**: `pip install -r requirements.txt`
2.  **Set up the database**: Manually create the database using a tool like `psql` and then run the `setup_database.sql` script.
3.  **Configure `.env`**: Create the `.env` file and set `DB_HOST=localhost`.
4.  **Update script paths**: Ensure the JSON directory path in `json_to_postgres_loader.py` and `test_json_files.py` points to the correct location on your local machine.
5.  **Run the scripts**: Execute `python json_to_postgres_loader.py` and then `python corpus_analyzer.py`.

--- 

## 📜 Component Documentation

| File                        | Description                                                                                                                                                                                                                                         |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Application Scripts**     |                                                                                                                                                                                                                                                     |
| `json_to_postgres_loader.py`| **The core ingestion engine.** A highly optimized, multiprocessing script that discovers, processes, and bulk-inserts JSON data into PostgreSQL. Features detailed progress, performance metrics, and error logging.                                        |
| `corpus_analyzer.py`        | **The RAG insights tool.** Queries the populated database to analyze text lengths, metadata completeness, and data distributions. It generates final recommendations and estimations for building an effective RAG system.                     |
| `fresh_database_setup.py`   | A developer utility script that **wipes the database clean**. It drops all tables and sequences and re-creates the schema from scratch, providing a fresh start for testing.                                                               |
| `test_connection.py`        | A simple pre-flight check to verify that the database connection settings in the `.env` file are correct and that the PostgreSQL server is reachable.                                                                                           |
| `test_json_files.py`        | A pre-flight check to verify that the specified JSON corpus directory exists and contains `.json` files, preventing the loader from running on an empty or misconfigured path.                                                              |
| **Docker Files**            |                                                                                                                                                                                                                                                     |
| `Dockerfile`                | Defines the container image. It starts with a `postgres:15` base image and adds a Python environment, all necessary system libraries, and the application code.                                                                                   |
| `docker-compose.yml`        | The orchestration file. Defines and configures the `postgres` and `pgadmin` services, their networking, ports, and a crucial volume mount that links your local JSON files to the container.                                                        |
| `docker-init.sh`            | An initialization script that runs automatically when the PostgreSQL container starts for the first time. It waits for the database to be ready and then executes `setup_database.sql` to create the table schema.                        |
| `docker-setup.bat`          | A convenience script for Windows users to build and start the Docker environment with a single command.                                                                                                                                          |
| **Configuration & Schema**  |                                                                                                                                                                                                                                                     |
| `.env`                      | Local configuration file (you must create this). Stores the database host, user, password, and port to keep credentials out of the source code.                                                                                            |
| `setup_database.sql`        | The canonical SQL schema definition. It contains the `CREATE TABLE` and `CREATE INDEX` statements needed to set up the `ecli_documents` table.                                                                                                |
| `requirements.txt`          | A list of all Python packages required by the project.                                                                                                                                                                                              |
| `DOCKER_README.md`          | A supplementary guide with more detailed Docker commands for advanced use cases like backup, restore, and performance tuning.                                                                                                                     |