# 🧠 Data Analytics AI Agent

> An AI-powered data analytics assistant that automates the entire data lifecycle — from ingestion to transformation, querying, visualization, and reporting.

Built with Python, FastAPI, Streamlit, and PostgreSQL, this agent serves as an end-to-end intelligent companion for data analysts, enabling seamless data management through automation and natural-language interaction.

---

## 🧩 Tech Stack

| Category | Tools |
|----------|-------|
| Languages | Python |
| Frameworks | FastAPI, Streamlit |
| Libraries | Pandas, NumPy, SQLAlchemy, LangChain |
| Database | PostgreSQL |
| Key Concepts | ETL Automation, NLP Querying, Data Validation, Visualization, Reporting |

---

## 🚀 Core Features

- **🧮 Multi-Source Data Input** — Supports CSV/XLSX uploads, API connections, and database linking.
- **🧹 Automated ETL Pipeline** — Cleans, validates, and transforms datasets to ensure data quality and schema consistency.
- **🧠 NLP-Based SQL Querying** — Query datasets in plain English, automatically converted into SQL.
- **📊 Dynamic Visualization** — Generate interactive charts and plots instantly.
- **📄 Automated Reporting** — Exports summarized insights as downloadable PDF/CSV reports.
- **🔐 Governed Workflows** — Modular backend design for secure and auditable data operations.

---

## 🎥 Demo

> ▶️ Watch on YouTube: https://youtu.be/zXhgjuuniIU?si=GSOOFEOWkTKzLj1H

💬 This version demonstrates the complete end-to-end workflow on a local environment. Cloud deployment (Streamlit/Google Cloud) is under final testing for public release.

---

## 🏗️ System Architecture Overview

```

┌────────────────────────────────────────┐
│Frontend (UI)             │
│Streamlit Application          │
└────────────────────────────────────────┘
│
▼
┌────────────────────────────────────────┐
│Backend (API Layer)              │
│FastAPI – Handles data flow & NLP SQL  │
└────────────────────────────────────────┘
│
▼
┌────────────────────────────────────────┐
│Data Processing Engine           │
│ETL Pipeline • Validation • Reporting  │
└────────────────────────────────────────┘
│
▼
┌────────────────────────────────────────┐
│PostgreSQL Database             │
│Structured Storage & Query Execution    │
└────────────────────────────────────────┘

```

---

## 📂 Project Structure

```

Data-Analytics-AI-Agent/
├── app.py          #streamlit app
├── modules
    ├── __init__.py
    ├── ai_services.py
    ├── data_cleaning.py
    ├── data_ingestion.py
    ├── database_manager.py
    ├── profiling.py
    └── visualization.py
├── tests/                # Unit tests
├── requirements.txt      # Project dependencies
├── requirements-dev.txt  # Dev dependencies
├── docker-compose.yml    # Docker compose configuration
├── Dockerfile            # Docker image definition
├── Makefile              # Task runner shortcuts
├── utils
    ├── __init__.py
    └── helpers.py
├── README.md            
├── CONTRIBUTING.md       # Contribution guidelines
├── CHANGELOG.md          # Project version history
├── .devcontainer
    └── devcontainer.json
├── .github/              # CI/CD and Templates
├── .gitignore
├── LICENSE


```

---

## 🧠 How It Works

1. **Ingest** data from multiple sources (upload, API, or DB).
2. **Validate and Clean** via automated ETL pipelines.
3. **Query** using natural language → converted into SQL.
4. **Visualize** patterns and metrics instantly.
5. **Export Reports** in multiple formats (Interactive-Web-report/Cleaned-CSV-data-export).

---

## 📈 Future Enhancements

- ☁️ Streamlit Cloud / GCP Deployment for scalable access.
- 🧾 Role-Based Access Control (RBAC) for governed environments.
- ⏱ Automated Scheduling & Reporting Pipelines.
- 🗃 Integration with BigQuery or Hive for big-data scalability.

---

## 🐳 Running with Docker

You can easily run this application without installing Python locally using Docker.
Ensure you have Docker and Docker Compose installed, then run:

```bash
docker-compose up -d
```
The app will be available at `http://localhost:8501`.

---

## 🤝 Contributing

We welcome contributions! Please see our [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to set up your development environment, run tests, and submit pull requests.

---

## 👨‍💻 Author

**shreyescodes**  
📍 Passionate Data Analyst | Focused on Big Data Analytics, AI Agents, and Workflow Automation

- GitHub: [See Projects here](https://github.com/shreyescodes)

---

## 📜 License

MIT License © 2025 shreyescodes
Feel free to fork, contribute, or enhance this project.