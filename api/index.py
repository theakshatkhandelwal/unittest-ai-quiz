from app import app

# This is the entry point for Vercel
# The app object from app.py is imported and used directly
application = app

if __name__ == "__main__":
    application.run()
