from app import create_app

app = create_app()

if __name__ == "__main__":
    # Never enable the interactive debugger outside local development.
    debug = app.config.get("APP_ENV") == "development"
    app.run(debug=debug)
