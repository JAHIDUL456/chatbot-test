# Production-Ready FastAPI & Groq base

This project implements a production-grade FastAPI base structure, configured for local containerized environment setup using Docker/Docker Compose and integrated with the Groq SDK using the high-performance `llama-3.3-70b-versatile` model.

## 🚀 Key Features

* **Asynchronous Integration**: Fully asynchronous I/O loops matching FastAPI's performance characteristics.
* **Environment-Driven Configuration**: Settings management powered by `pydantic-settings` to guarantee validation on startup.
* **Self-Documenting Swagger Endpoint**: Detailed typing parameters using Pydantic Models for automated OpenAPI generation at `/docs`.
* **Structured Logger Setup**: Centralized custom logging configuration.
* **Containerized Development Environment**: Streamlined setup using Docker and Docker Compose.

---

## 📁 Repository Structure

```text
ai-test/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── __init__.py
│   │   │   │   └── chat.py         # Chat completion route handler
│   │   │   ├── __init__.py
│   │   │   └── api.py              # Main v1 router aggregating endpoints
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py           # Configuration schema validations
│   │   │   └── logger.py           # Logger bootstrap functions
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── chat.py             # Pydantic validation schemas
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   └── groq_client.py      # Async client logic for Groq endpoints
│   │   ├── __init__.py
│   │   └── main.py                 # Application bootstrap entrypoint
├── .env                            # Local configuration settings (contains API key)
├── .env.example                    # Template for config file
├── Dockerfile                      # Server image blueprint
├── docker-compose.yml              # Local container orchestrator configuration
├── requirements.txt                # Third-party dependency definitions
└── README.md                       # Setup & usage instructions
```

---

## 🛠️ Environment Configuration

Configurations are loaded dynamically from the `.env` file at the root of the project.

Key parameters in `.env`:
* `PROJECT_NAME`: Display name of the API project in Swagger UI.
* `DEBUG`: Toggle detailed log levels.
* `API_V1_STR`: Global prefix for routes.
* `GROQ_API_KEY`: Groq authentication token.
* `GROQ_MODEL`: Groq Model ID (Defaults to `llama-3.3-70b-versatile`).

---

## 🐋 Setup & Running with Docker (Recommended)

To run the application inside docker container in hot-reload mode:

1. **Start the API Server**:
   ```bash
   docker compose up --build
   ```
2. **Access Swagger Documentation**:
   Navigate to [http://localhost:8000/docs](http://localhost:8000/docs) in your web browser.

---

## 🐍 Running Locally (Without Docker)

Ensure you have Python 3.10+ installed on your system:

1. **Create and Activate a Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the FastAPI App**:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
4. **Access the Documentation**:
   Navigate to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

## 🧪 Testing the API

You can test the endpoint `/api/v1/chat/` directly from the interactive docs `/docs` page or use the command line:

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Explain quantum computing in one sentence."}
    ],
    "temperature": 0.7
  }'
```
