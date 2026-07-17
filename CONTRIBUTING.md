# Contributing to Data Analytics AI Agent

First off, thank you for considering contributing to this project! It's people like you that make the open-source community such a fantastic place to learn, inspire, and create.

## 🛠️ Development Setup

To get started with local development, follow these steps:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/shreyescodes/Data-Analytics-AI-Agent.git
   cd Data-Analytics-AI-Agent
   ```

2. **Set up your environment:**
   We use a `Makefile` to simplify setup. Run the following command to install the application dependencies and development dependencies (`pytest`, `black`, `flake8`):
   ```bash
   make install-dev
   ```

3. **Install Pre-commit Hooks:**
   We enforce formatting and linting via `pre-commit`. Install the hooks to ensure your code is automatically formatted before you commit:
   ```bash
   pre-commit install
   ```

4. **Run the application locally:**
   ```bash
   make run
   ```

## ✅ Testing & Linting

Before submitting a Pull Request, please ensure all checks pass:

- **Run Linters (flake8, black, isort):**
  ```bash
  make lint
  ```
- **Run Unit Tests:**
  ```bash
  make test
  ```

## 🐳 Docker

If you prefer to develop using Docker, you can build and run the application container using:
```bash
make build
make up
```

## 📝 Pull Request Process

1. Ensure any new functionality includes tests.
2. Update the `README.md` and `CHANGELOG.md` with details of changes if applicable.
3. Your code must pass the GitHub Actions CI pipeline.
4. When opening a PR, fill out the provided Pull Request Template completely.
