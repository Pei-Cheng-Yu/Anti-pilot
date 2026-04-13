<<<<<<< Updated upstream
﻿# Anti-pilot

## How to run

> [!NOTE]
> The commands might not apply to Windows users
> This project requires **Python  3.11+**.

1. Install [pyenv](https://github.com/pyenv/pyenv) or [pyenv-win](https://github.com/pyenv-win/pyenv-win) (windows)
2. Install python 3.11 with pyenv, then `cd` into this project, the 3.11 version will be used due to the `.python-version` file of this project

   ```bash
    pyenv install 3.11
   ```

3. Create virtual environment and source it

   MacOS/Linux

   ```bash
   python -m venv venv # create venv in venv directory
   source ./venv/bin/activate # change this path according to your shell type
   ```

   Windows

   ```bash
   python -m venv venv # create venv in venv directory
   .\venv\Scripts\activate # change this path according to your shell type
   ```

4. Install dependencies

   ```bash
   pip install -r requirements.txt
   pre-commit install --install-hooks # install pre-commit hooks for auto format after every commit
   ```

5. Create `.env` from `example.env`: `cp example.env .env`, then modify the content in `.env`
6. Run test for current graph, and tracing on LangSmith
   > make sure u set up the `.env`

    Start the development server to connect your agent to LangSmith Studio:
    ```
    cd backend
    langgraph dev
    ```
    Run test
    ```
    cd backend
    python -m tests.test_planner_to_evaluate  //can replace with other file in /backend/tests
    ```



=======
# Anti-pilot

## Docs

- [Project Docs](docs/README.md)

## How to run

> [!NOTE]
> The commands might not apply to Windows users
> This project requires **Python  3.11+**.

1. Install [pyenv](https://github.com/pyenv/pyenv) or [pyenv-win](https://github.com/pyenv-win/pyenv-win) (windows)
2. Install python 3.11 with pyenv, then `cd` into this project, the 3.11 version will be used due to the `.python-version` file of this project

   ```bash
    pyenv install 3.11
   ```

3. Create virtual environment and source it

   MacOS/Linux

   ```bash
   python -m venv venv # create venv in venv directory
   source ./venv/bin/activate # change this path according to your shell type
   ```

   Windows

   ```bash
   python -m venv venv # create venv in venv directory
   .\venv\Scripts\activate # change this path according to your shell type
   ```

4. Install dependencies

   ```bash
   pip install -r requirements.txt
   pre-commit install --install-hooks # install pre-commit hooks for auto format after every commit
   ```

5. Create `.env` from `example.env`: `cp example.env .env`, then modify the content in `.env`
6. Run test for current graph, and tracing on LangSmith
   > make sure u set up the `.env`

    Start the development server to connect your agent to LangSmith Studio:
    ```
    cd backend
    langgraph dev
    ```
    Run test
    ```
    cd backend
    python -m tests.test_planner_to_evaluate  //can replace with other file in /backend/tests
    ```
>>>>>>> Stashed changes
