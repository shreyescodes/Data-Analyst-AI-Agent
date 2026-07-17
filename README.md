# Data Analytics AI Agent

A data analytics tool that automates the entire data lifecycle — from data ingestion to transformation, querying, visualization, and reporting.

Built using Python, FastAPI, Streamlit, and PostgreSQL. It acts as an end-to-end tool for data analysts, making data management simple through automation and natural-language interaction.

---

## Tech Stack

| Category | Tools |
|----------|-------|
| Languages | Python |
| Frameworks | FastAPI, Streamlit |
| Libraries | Pandas, NumPy, SQLAlchemy, LangChain |
| Database | PostgreSQL |
| Key Concepts | ETL Automation, NLP Querying, Data Validation, Visualization, Reporting |

---

## Core Features

- **Multi-Source Data Input**: Supports CSV/XLSX file uploads, API connections, and direct database linking.
- **Automated ETL Pipeline**: Cleans, validates, and transforms datasets to ensure data quality and schema consistency.
- **NLP-Based SQL Querying**: Query your datasets using plain English, which gets converted into SQL queries.
- **Dynamic Visualization**: Generate interactive charts and plots instantly.
- **Automated Reporting**: Export insights as downloadable PDF or CSV reports.
- **Governed Workflows**: Modular backend design for secure and auditable data operations.

---

## System Architecture Overview

```text
┌────────────────────────────────────────┐
│Frontend (UI)                           │
│Streamlit Application                   │
└────────────────────────────────────────┘
│
▼
┌────────────────────────────────────────┐
│Backend (API Layer)                     │
│FastAPI - Handles data flow & NLP SQL   │
└────────────────────────────────────────┘
│
▼
┌────────────────────────────────────────┐
│Data Processing Engine                  │
│ETL Pipeline, Validation, Reporting     │
└────────────────────────────────────────┘
│
▼
┌────────────────────────────────────────┐
│PostgreSQL Database                     │
│Structured Storage & Query Execution    │
└────────────────────────────────────────┘
```

---

## Project Structure

```text
Data-Analytics-AI-Agent/
├── app.py                # Streamlit app
├── modules/
│   ├── __init__.py
│   ├── ai_services.py
│   ├── data_cleaning.py
│   ├── data_ingestion.py
│   ├── database_manager.py
│   ├── profiling.py
│   └── visualization.py
├── tests/                # Unit tests
├── requirements.txt      # Project dependencies
├── requirements-dev.txt  # Dev dependencies
├── docker-compose.yml    # Docker compose configuration
├── Dockerfile            # Docker image definition
├── Makefile              # Task runner shortcuts
├── utils/
│   ├── __init__.py
│   └── helpers.py
├── README.md            
├── CONTRIBUTING.md       # Contribution guidelines
├── CHANGELOG.md          # Project version history
├── .devcontainer/
│   └── devcontainer.json
├── .github/              # CI/CD and Templates
├── .gitignore
└── LICENSE
```

---

## How It Works

1. **Ingest** data from multiple sources (upload, API, or Database).
2. **Validate and Clean** via automated ETL pipelines.
3. **Query** using natural language which gets converted into SQL.
4. **Visualize** patterns and metrics instantly.
5. **Export Reports** in multiple formats like interactive web reports or cleaned CSV files.

---

## Future Enhancements

- Streamlit Cloud or GCP deployment for scalable access.
- Role-Based Access Control (RBAC) for governed environments.
- Automated scheduling and reporting pipelines.
- Integration with BigQuery or Hive for big-data scalability.

---

## Running with Docker

You can easily run this application without installing Python locally by using Docker.
Ensure you have Docker and Docker Compose installed on your machine, then run:

```bash
docker-compose up -d
```
The application will be available at `http://localhost:8501`.

---

## Contributing

We welcome contributions. Please see our [CONTRIBUTING.md](CONTRIBUTING.md) file for details on how to set up your local development environment, run tests, and submit pull requests.

---

## Author

**shreyescodes**  
- GitHub: [shreyescodes](https://github.com/shreyescodes)

---

## License

MIT License (c) 2025 shreyescodes.  
Feel free to fork, contribute, or enhance this project.