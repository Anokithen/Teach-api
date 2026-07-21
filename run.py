from app import create_app

app = create_app()

with app.app_context():
    from app.extensions import db
    db.create_all()

if __name__ == "__main__":
    import os
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
