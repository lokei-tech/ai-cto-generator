# AI CTO Generator

## Project Description
AI CTO Generator is a Python-based application designed to assist in generating technical specifications and guidance for software projects. Utilizing the OpenAI Large Language Model (LLM) API, this tool integrates a customtkinter GUI to provide a user-friendly interface for developers.

## Installation Instructions

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/lokei-tech/ai-cto-generator.git
   cd ai-cto-generator
   ```

2. **Create a Virtual Environment:**
   ```bash
   python -m venv env
   source env/bin/activate  # On Windows use `env\Scripts\activate`
   ```

3. **Install Requirements:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

To use this application, you need to configure your API keys for the LLM providers:

1. Create a `.env` file in the root of the project.
2. Add the following lines to the `.env` file:
   ```
   OPENAI_API_KEY=your_openai_api_key
   ```

Replace `your_openai_api_key` with your actual API key.

## Usage Guide

1. Run the application:
   ```bash
   python main.py
   ```

2. Follow the on-screen instructions to generate technical specifications.

3. Ensure your LLM provider's API is configured correctly to allow the application to function.